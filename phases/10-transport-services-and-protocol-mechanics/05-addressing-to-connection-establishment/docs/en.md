# Addressing to Connection Establishment

> Before two transport entities can exchange a single byte they must agree on three things: **who is being addressed** (a TSAP like TCP port 1522 mapped to a NSAP like 192.168.1.1), **how to find a peer that may not have a stable address** (a portmapper, an inetd-style process server, or DNS SRV), and **how to start a connection that survives delayed duplicates** (Tomlinson's clock-based initial sequence number, refined by Sunshine and Dalal, and instantiated as the three-way handshake TCP uses today). The Internet takes the packet-lifetime constant to be 120 s; everything in this lesson - the T=120 s wait, the clock-driven 32-bit ISN, the SYN/SYN+ACK/ACK exchange, and the rejection of stale CRs - is calibrated to that number.

**Type:** Build
**Languages:** Python (stdlib-only addressing and three-way-handshake simulator)
**Prerequisites:** Berkeley Sockets (lesson 03), Transport Service Primitives (lesson 02)
**Time:** ~80 minutes

## Learning Objectives

- Draw the TSAP/NSAP layering (Fig. 6-8) and explain why one host can serve many transport endpoints on a single IP address via port numbers, and how a process server (inetd) can spawn a server on demand when a request arrives for a TSAP that has no live listener.
- Implement the clock-based initial sequence number (ISN) scheme of Tomlinson (1975): the low-order 32 bits of a binary counter that keeps running across host crashes, ensuring that two `CONNECT` attempts separated by more than 120 s never reuse the same ISN.
- Trace a TCP three-way handshake step by step (CR with ISN=x, ACK with ISN=y and ack=x, DATA/ACK with seq=x+1 and ack=y+1) and show how the second ACK prevents a delayed-duplicate CR from accidentally establishing a connection.
- Distinguish the four packet-lifetime bounding techniques (restricted network design, hop counter, timestamp, wait-T-secs) and explain why the Internet uses hop count plus a 120-s TIME_WAIT, and not a synchronized timestamp.
- Explain why a "two-army"-style absolute agreement on connection state cannot be guaranteed over an unreliable channel, and how TCP's three-way handshake sidesteps this for the *opening* case at the cost of letting one side unilaterally time out.

## The Problem

A network operations team has an outage: an automation system tries to open a TCP connection to a service that was restarted 30 seconds ago. The connect succeeds at the kernel level - the SYN goes out, the SYN+ACK comes back, the ACK goes out - but the application sees the new connection "steal" state from a previous connection that the kernel still has in TIME_WAIT. Symptoms include corrupted data at the start of the stream and a service that "works for 30 seconds after a restart, then mysteriously misbehaves." The on-call engineer reads the RFCs and finds out that the only thing standing between them and chaos is an ISN chosen to never repeat inside the maximum packet lifetime (120 s), and a TIME_WAIT long enough to drain the network of stale segments.

A second team has the opposite problem: a client process that should connect to a mail server on host B, port 25, cannot find it because the mail server is not always running. The fix is `inetd` (or `systemd` socket activation): a process server that listens on the well-known port and spawns the actual server on the first SYN. Without understanding the TSAP/NSAP layering and the portmapper pattern, the engineer cannot even frame the question.

This lesson is the source-of-truth for both problems: addressing plus the establishment protocol that defends against the network's tendency to misbehave.

## The Concept

### TSAPs, NSAPs, and the portmapper

A **TSAP** (Transport Service Access Point) is the transport-layer name of an endpoint; in the Internet, a TSAP is the pair `(IP address, 16-bit port)`. An **NSAP** (Network Service Access Point) is the network-layer name; in IPv4, an NSAP is the IP address itself. Many TSAPs share one NSAP: a single web server listens on 192.168.1.1:80, 192.168.1.1:443, 192.168.1.1:8080, 192.168.1.1:8443, all the same host, all the same IP. The transport entity demultiplexes incoming segments to the right socket by reading the destination port.

How does a client learn the TSAP of a service it has never contacted? Three schemes:

1. **Stable, well-known TSAPs** - `/etc/services` lists port 25 as SMTP, 80 as HTTP, 443 as HTTPS. Used for services that run forever.
2. **Portmapper** - the client connects to a well-known portmapper TSAP (port 111 on UNIX), sends the service name, and receives a `(host, port)` pair to use for the real connection. Like the operator in a telephone system.
3. **Process server (inetd)** - a single process listens on a *set* of TSAPs at once. When a SYN arrives for one of them, inetd accepts, forks the actual server, and hands off the connected socket. The actual server only runs while it is needed.

```
   client            inetd (process server)         mail server
     |   SYN to TSAP 25   |                              |
     | -----------------> | accept(); fork()            |
     |                     | ----------------------> exec(maild)
     |   SYN+ACK           |                              |
     | <----------------- | <----- dup(fd) ------------> |
     |   ACK               |                              |
     | -----------------> |                              |
     |   DATA              |                              |
     | ------------------------------------------> read() |
```

inetd's `dup(fd)` is what makes the trick work: the connected socket is passed to the child, which then reads and writes on it as if it had done the `accept` itself.

### The delayed-duplicate problem

If the network can drop, delay, reorder, and duplicate packets, a "send a CR, wait for ACK" protocol is not enough. Tomlinson's nightmare: a client connects to a bank, sends a money transfer, the connection completes, the bank acts on it. Then *an hour later*, a delayed duplicate of the original CR arrives at the bank, the bank thinks it is a new connection, and the transfer happens twice.

The textbook's three defenses:

1. **Throwaway transport addresses** - generate a fresh TSAP for every connection, never reuse. Secure but impractical: callers cannot find a service that has no fixed address.
2. **Unique connection identifiers** - tag every connection with a sequence number from a global counter; the receiver remembers recently-used IDs and rejects duplicates. Requires the receiver to keep state forever, which fails across a host crash.
3. **Bound the packet lifetime** - guarantee that no packet (and no ACK of it) can live in the network for more than T seconds. Then the only way a duplicate can affect a new connection is if the new connection reuses a sequence number inside the T-second window. Pick sequence numbers that do not wrap inside T.

The Internet uses #3, with T=120 s (somewhat arbitrarily, see Tanenbaum §6.2.2).

### Bounding the packet lifetime

The textbook lists three implementation techniques. The Internet uses a hop count (the IP `TTL` field, originally meant to bound lifetime, now used mainly to prevent routing loops) plus a passive time bound (every TCP endpoint that closes a connection enters TIME_WAIT for 2 * MSL, where MSL is typically 60 s, giving the 120-s window). Timestamps would require synchronized clocks, which is a hard distributed-systems problem, so they are not used for this purpose at the IP layer. RFC 1323's PAWS (Protection Against Wrapped Sequence numbers) does use timestamps, but to defend a different problem - sequence-number wraparound on long-fat pipes, not delayed duplicates.

### Tomlinson's clock-based ISN

The textbook's key insight: if every host has a **monotonic binary counter that runs even when the host is powered off**, then the low-order k bits of the counter make perfect initial sequence numbers. Two connections established more than T seconds apart will have ISNs that differ by more than `C * T` (where C is the number of ISNs per second), which is large enough that no delayed duplicate of the first can impersonate the second. Concrete numbers from the textbook:

- Clock tick rate: 1 microsecond or less
- Sequence number space: S = 2^32
- Required inequality: `S / C > T`, so `2^32 / (1e6) = 4294 s > 120 s`. Check.

The "forbidden region" in Fig. 6-10(a) is the set of ISNs that, if used, *could* be impersonated by a delayed duplicate of an earlier connection. The rule is: never send a packet with a sequence number inside the forbidden region (the most recent 2^32 sequence numbers issued by the network, roughly speaking).

Modern TCP replaces the clock with a **cryptographic pseudorandom number generator** (RFC 6528), but the same invariant holds: the ISN must not repeat within the maximum packet lifetime. The clock scheme has a known security weakness - the ISN is predictable, which lets an attacker forge packets - so the PRNG scheme is now standard. The lesson, however, is the principle: pick ISNs that do not repeat inside T.

### The three-way handshake (Fig. 6-11)

Tomlinson's 1975 protocol, refined by Sunshine and Dalal (1978), is what TCP uses today:

```
   Host 1 (client)                          Host 2 (server)
   ---------------                          ---------------
   1. CR(seq=x)
       ---------------------------------->
                                              2. ACK(seq=y, ack=x)
                                          <----------------------------------
   3. DATA(seq=x+1, ack=y+1)
       ---------------------------------->
```

Step 1: the client picks an ISN `x` and sends a CONNECTION REQUEST segment containing it.
Step 2: the server picks its own ISN `y` for traffic in the opposite direction, acknowledges `x` (so the client knows the server received `x`), and sends both values back.
Step 3: the client acknowledges `y` (so the server knows the client received `y`) and starts sending data with `seq = x+1`.

The crucial property: the server's `y` is *not* acknowledged until step 3. If step 3 never arrives, the server concludes the connection was a duplicate and drops it.

### Defending against delayed duplicates

Three scenarios from Fig. 6-11:

**(a) Normal operation.** Client picks `x`, server picks `y`, both confirmed. The connection is established; data flows.

**(b) Old duplicate CR arrives at the server.** The server sends `ACK(seq=y, ack=x)`, but the client has no record of having sent `x`. The client sends a `REJECT(ack=y)` segment, and the server knows the CR was a duplicate and tears the half-open state down.

**(c) Old duplicate CR *and* old duplicate ACK both arrive at the server.** The first duplicate CR triggers a fresh `y`. The second duplicate ACK has `z` (a different old sequence number). The fact that the server has now seen an `ack=z` rather than `ack=y` tells it that the second message is also an old duplicate, and the connection is rejected.

The textbook's summary is precise: *"no combination of old segments can cause the protocol to fail and have a connection set up by accident when no one wants it."*

### Why three, not two

A two-message handshake (CR, ACK) does not work: if the server's ACK is lost, the client retransmits the CR, and the server has no way to tell the second CR from a brand-new connection attempt. With a third message, the client confirms the server's ISN, and the server can detect a stale CR by the absence of that confirmation. The two-army problem (next subsection) shows that even three messages are not *quite* enough for absolute agreement, but they are enough for the practical case.

### The two-army problem and why it does not kill the handshake

The two-army problem (Fig. 6-13): two armies must agree to attack at dawn over an unreliable messenger channel. No finite number of messages is sufficient, because the last message of any protocol is either essential (and so can be lost) or inessential (and so can be removed). TCP's three-way handshake sidesteps the issue by being **asymmetric**: the client's step 3 is *not* essential for the client to proceed - if it is lost, the client retransmits the CR. The server can always time out and release the half-open state. The cost: TCP can have a half-open connection after enough retransmissions fail. The fix: a keep-alive timer (typically 2 hours) that drops the connection if no traffic flows.

## Build It

`code/main.py` implements the addressing and three-way-handshake logic in pure Python:

1. **TSAP / NSAP mapping** - a `TSAP(host, port)` type, a `Portmapper` directory service (the well-known port 111 model), and an `Inetd` process server that spawns a real handler on the first SYN to a TSAP it owns.
2. **Clock-based ISN generator** - a `Clock` that ticks at 1 MHz, and an `ISNAllocator` that returns the low-order 32 bits. The simulator's clock persists across simulated crashes, matching the textbook's requirement.
3. **Three-way handshake** - `cr`, `ack`, `data` messages with sequence numbers; the server stores the `y` it offered; the client acknowledges `y` in its first data segment. Replay attempts (old CR, old ACK) are detected and rejected.
4. **Two-army proof-of-impossibility** - a small search shows that for any N-message protocol over a lossy channel, there is a message whose loss breaks synchronization. The simulator walks a 3-message protocol and shows the failure mode.

Run with `python3 code/main.py`. Watch the ISN values - they increment by one per simulated microsecond - and confirm that an ISN generated at t=0 and one at t=200 s cannot be confused by a delayed duplicate at t=10 s.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Map a TSAP to a process | `getpeername()` / `getsockname()` | A TSAP `(10.0.1.5, 25)` maps to inetd at boot and to a real maild once a connection arrives |
| Choose an ISN | `seq=3700000000` and the clock | ISN chosen from the low 32 bits of a counter that ticks at >= 1 us, never reuses a value inside 120 s |
| Trace a 3-way handshake | SYN, SYN+ACK, ACK with seq/ack | First data segment's `seq = x+1`, `ack = y+1` |
| Detect a delayed duplicate CR | `REJECT(ack=y)` from the client | Server tears down the half-open state; no application data is delivered |
| Bound packet lifetime | `TIME_WAIT = 2 * MSL = 120 s` | Both peers wait long enough for stray segments to drain from the network |
| Reason about the two-army problem | the last-message-loss argument | For any N, the protocol fails on a single loss; the workaround is unilateral timeout |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **TSAP/NSAP reference card** showing the demultiplexing flow and the three address-discovery mechanisms (stable, portmapper, process server).
- A **3-way-handshake dissection** that annotates every flag and sequence number in a real `tcpdump -Sni lo0 port 12345` capture of a localhost `nc -l 12345 &; nc localhost 12345` session.
- A **delayed-duplicate attack runbook** - how to reproduce, how to detect (look for an `RST` from the client), and how RFC 6528's PRNG-based ISN defends.
- A **two-army proof sketch** - the one-paragraph proof that no N-message protocol over a lossy channel can guarantee agreement.

Start from `outputs/prompt-addressing-connection-establishment.md`.

## Exercises

1. A host's clock ticks at 1 MHz. The sequence-number space is 2^32. What is the maximum safe T (maximum packet lifetime) under the inequality `S / C > T`? What if the clock ticks at 1 GHz?
2. A client picks ISN `x = 0xCAFEBABE` and sends a CR. The server replies with `seq = y = 0xDEADBEEF, ack = 0xCAFEBABE`. The client's `ack` (step 3) is lost. Does the connection establish? What does the client do next? What does the server do?
3. inetd listens on ports 25, 80, and 443. A SYN arrives at port 80. What does inetd do with the connected socket before exec()ing the web server?
4. The textbook says T = 120 s for the Internet. The retransmission timeout for a SYN retransmit is typically 75 s. What happens if a delayed CR is in the network for 90 s and the original CR's retransmit is also in the network? Sketch the timeline.
5. The two-army proof shows that no finite protocol guarantees agreement over a lossy channel. TCP gets away with it by being asymmetric - one side can unilaterally give up. Name two other real-world protocols that use the same trick and one that does not (and explain the difference).
6. Run `code/main.py`'s handshake simulator with a clock skew of -10 s on the client. Is the connection still established? What does the server see in the third segment?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| TSAP | "a port" | Transport Service Access Point; in TCP/IP, the pair `(IP, port)` that names one transport endpoint on one host |
| NSAP | "an IP address" | Network Service Access Point; the network-layer name. IP addresses are NSAPs |
| Portmapper | "the directory service" | A well-known service that maps service names to `(host, port)` pairs; lives on port 111 (UNIX) historically |
| Inetd | "the super-server" | A process server that listens on a set of TSAPs and forks the right program on the first SYN |
| ISN | "initial sequence number" | The first sequence number a transport entity uses on a new connection; must be unique inside the maximum packet lifetime |
| Three-way handshake | "SYN, SYN+ACK, ACK" | Tomlinson's 1975 establishment protocol; defends against delayed duplicates by having the client confirm the server's ISN in a third message |
| Forbidden region | "the ISNs you cannot use" | The set of sequence numbers that, if used, could be impersonated by a delayed duplicate |
| TIME_WAIT | "the 2 * MSL wait" | The 120-s hold after active close that lets stray segments drain; central to making delayed-duplicate defense work |
| Two-army problem | "synchronization is impossible" | A 1975 impossibility result: no finite protocol over a lossy channel can guarantee two parties reach agreement |

## Further Reading

- **Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §6.2.1-6.2.2** - the source chapter for this lesson (Figs. 6-8, 6-10, 6-11).
- **Tomlinson, R. S. (1975), "Selecting sequence numbers," in *Proceedings of the IFIP WG6.4 International Workshop on Protocols for Satellite and Packet-Switched Networks*** - the original clock-based ISN paper.
- **Sunshine, C. A. & Dalal, Y. K. (1978), "Connection management in transport protocols," *Computer Networks* 2(4-5)** - the three-way handshake refinement.
- **RFC 793** (1981), "Transmission Control Protocol," §3.4 - "Establishing a Connection" - TCP's instantiation of the three-way handshake.
- **RFC 1323** (1992), "TCP Extensions for High Performance" - PAWS (Protection Against Wrapped Sequence numbers) and the high-speed timestamp option.
- **RFC 6528** (2012), "Defending against Sequence Number Attacks" - the case for cryptographic ISNs and the deprecation of the clock-based scheme.
- **Akkawi, A. & Bohn, R. (2007), "An introduction to the two-army problem and the Byzantine Generals problem"** - a clean write-up of the two-army impossibility.
