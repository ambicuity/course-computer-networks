# TSAPs, NSAPs, and the portmapper-based initial connection protocol

> The transport layer addresses processes, not hosts. A **TSAP** (Transport Service Access Point) is the endpoint a process listens on — in the Internet, a 16-bit port number (TCP or UDP). An **NSAP** (Network Service Access Point) is the endpoint the network layer addresses — an IPv4 or IPv6 address. Stacking one host's NSAP and many TSAPs gives every process on every host a unique address in the `(NSAP, TSAP)` pair. This lesson implements the chapter's portmapper (RFC 1833, the historical "rpcbind" model) and the *initial connection protocol* (Figure 6-9), the trick `inetd` still uses to avoid running a process for every rare service. The companion `code/main.py` is a stdlib-only portmapper simulator: it registers services by name (e.g. "BitTorrent" -> port 6881), answers a `GETPORT` query with the registered port, and runs the inetd-on-demand spawn pattern when a connection arrives at a service the host has never had running. The output mirrors the segment sequence Figure 6-9(b) shows: client -> process server -> fork(server) -> inherit connection.

**Type:** Build
**Languages:** Python, shell
**Prerequisites:** Phase 00 lab environment; lesson 14 (Berkeley socket API); basic fork/exec model
**Time:** ~90 minutes

## Learning Objectives

- Distinguish TSAPs (process endpoints) from NSAPs (host endpoints) and predict the role of each in a transport connection.
- Implement a portmapper in pure Python that maps `(program, version, protocol)` triples to ephemeral port numbers and answers `GETPORT` queries.
- Walk the initial connection protocol from Figure 6-9: client connects to a process server, process server forks the requested server, the child inherits the connection.
- Trace why well-known TSAPs (TCP 22, 25, 80, 443) are listed in `/etc/services` while most service TSAPs are dynamic.
- Reason about the security implication of binding to a privileged port (< 1024) and the modern `rpcbind` family of portmapper services.
- Use `code/main.py` to register services, query them, and simulate the inetd-style on-demand spawn.

## The Problem

You are asked to design the service discovery layer for a private network of three application servers. Some services (HTTP, SSH) are always running and bind to well-known ports from `/etc/services`. Others (a nightly report generator, an experimental chat service) run for minutes per day. If every service binds a port permanently, you waste dozens of port slots and dozens of `LISTEN()` FDs. If you let services pick their own ports dynamically, the clients have no way to find them.

This is the problem the chapter's portmapper solves. A single, well-known process — the portmapper — listens on TCP/UDP 111 and answers queries like `"What port is BitTorrent on this host?"` with the actual TSAP. New services register themselves with the portmapper on startup. The well-known TSAP of the portmapper is the one address every client can hard-code; everything else is dynamic.

A second design point is the *initial connection protocol* of Figure 6-9. Even the portmapper wastes a port per service. The initial connection protocol lets a *process server* (modern name: `inetd` or `systemd` socket activation) listen on behalf of *many* services. The first connection to TSAP 1234 wakes the process server, which forks the appropriate daemon, hands it the connection FD, and goes back to sleep. The cost of a rare service is now a single `LISTEN()` FD and zero processes until first use.

## The Concept

### TSAPs and NSAPs, the four-quadrant picture

Figure 6-8 of the chapter draws a transport connection as two TSAPs joined by a network path that runs through two NSAPs. The four numbers fully identify any connection:

| Level | Internet name | Size | Example |
|---|---|---|---|
| NSAP (host) | IP address | 32 (IPv4) or 128 (IPv6) bits | `192.0.2.7` |
| TSAP (process) | Port | 16 bits | `80` |
| Transport protocol | TCP or UDP | 8 bits | `TCP` (6) |
| Application | DNS, HTTP, SSH, ... | text | `http` |

A process that wants to be reachable attaches itself to a local TSAP via `BIND()` and waits. A peer process on a remote host attaches to its own local TSAP and issues `CONNECT(remote_NSAP, remote_TSAP)`. The transport entity on each side stitches the four numbers into a 5-tuple that uniquely identifies the connection in the kernel's TCB table. Multiple processes on the same host share the same NSAP but live on different TSAPs; that's multiplexing (lesson 17).

The portmapper (and `rpcbind`, its Sun RPC successor) is itself a server that binds a well-known TSAP and answers "what is the TSAP for service X?" from a database it has built up from prior registrations. RFC 1833 specifies the wire protocol: a 32-bit transaction ID, a 32-bit message type, and a port number in the response. The modern implementation on Linux is `rpcbind` (since glibc dropped Sun RPC's `portmap` in 2005); it listens on TCP/UDP 111 and serves `PMAPPROC_GETPORT` and `PMAPPROC_DUMP` calls.

### Well-known ports and the `/etc/services` contract

The IANA assigns well-known TSAPs from 0 to 1023 for privileged services (HTTP 80, HTTPS 443, SSH 22, SMTP 25, DNS 53). Ports 1024-49151 are "registered" — anyone can request a number, but the assignment is coordinated so the same number is not reused for incompatible services (e.g. 5432 is PostgreSQL, 3306 is MySQL). Ports 49152-65535 are "dynamic" or "ephemeral" — the kernel picks from this range for outgoing connections, and portmapper-registered services often land here.

The `/etc/services` file on every Unix-like system is the local copy of the IANA registry. It is a flat text file of `name port/protocol aliases`. `getent services http` returns `http 80/tcp`; that is the well-known TSAP HTTP servers bind. The kernel's own port allocator for ephemeral ports is `/proc/sys/net/ipv4/ip_local_port_range`, typically 32768-60999 on Linux.

The separation of well-known and dynamic is not arbitrary. It lets clients hard-code the port of the portmapper itself (111) and learn everything else at runtime. Without this, every new service would require updating every client. The well-known TSAP is the seed; everything else is a tree grown from it.

### The portmapper protocol

A portmapper interaction has three phases:

1. **Server side**: a service starts, picks a random free port, calls `BIND()` and `LISTEN()`, then sends a `PMAPPROC_SET` UDP datagram to the portmapper on TSAP 111. The datagram carries `(program, version, protocol, port)`. The portmapper records the tuple.

2. **Client side**: a client wants the service. It sends a `PMAPPROC_GETPORT` UDP datagram to the portmapper asking for `(program, version, protocol)`. The portmapper replies with the port number (or 0 if no match).

3. **The client opens a real connection** to the port the portmapper gave it, and the service runs.

The portmapper is one indirection: every service registration is one UDP datagram in, every service lookup is one UDP datagram in and one out, and the real connection is opened directly between client and server — the portmapper is not on the data path. This is why the portmapper is not a bottleneck: it handles only control traffic, never application data.

The on-wire format is XDR (RFC 4506), which is why Python programmers usually use a library rather than hand-rolling. The portmapper in `code/main.py` uses a simplified JSON-in-TCP format because the lesson is about the indirection, not the wire format. RFC 1833 §2 contains the canonical RPC definitions.

### The initial connection protocol and `inetd`

Figure 6-9 of the chapter shows the trick that `inetd` (Internet super-server, RFC 864 / 1236 / 1415) put into production in 4.3BSD (1986) and that `systemd` socket activation (2010) generalised. The mechanism is:

- One process (`inetd`) listens on a *set* of TSAPs at once. On Linux, this is `select()` / `poll()` over many FDs.
- When a connection arrives on TSAP X, `inetd` looks up which service is registered for X.
- `inetd` `fork()`s, `exec()`s the registered service binary, and crucially: passes the *connected socket FD* to the child via the standard FDs 0, 1, 2.
- The child runs the service, which reads from FD 0 (the connection), does its work, writes to FD 1, and exits. `inetd` parent goes back to listening.

The advantage: services that are rarely used (talk, ntalk, finger, time) consume *no* resources until a packet arrives. The cost: the service cannot have its own state across connections, and the cold-start latency is the fork+exec of the daemon. For long-running services (web servers, databases), the modern pattern is to `bind` a port from a systemd unit and run as a regular daemon.

The `initial connection protocol` in the chapter is exactly the connection-arrives-then-fork pattern. The phrase "process server" in Figure 6-9 is what we now call `inetd` or `systemd` socket activation.

### Why this is no longer how modern microservices work

The portmapper pattern assumes a stable network of services that come and go. Modern systems have replaced it with three patterns:

1. **Service registries** (Consul, etcd, Zookeeper): like a portmapper but reachable over HTTP and watched for changes.
2. **DNS SRV records** (RFC 2782): the well-known TSAP moves into DNS. `_http._tcp.example.com. SRV 0 5 80 server1.example.com.`
3. **Environment variables and sidecar discovery** (Kubernetes): the orchestrator injects the service address into the pod.

The portmapper is still in use because the Sun RPC ecosystem (`rpcbind`, NFS, NIS) is huge and was not retrofitted. Understanding the portmapper teaches the principles of dynamic service discovery even if you do not use it.

### Failure modes

| Symptom | Root cause | Fix |
|---|---|---|
| `clnt_create: RPC: Port mapper failure` | `rpcbind` is not running | Start `rpcbind` (or `systemctl start rpcbind`) |
| `clnt_create: RPC: Program not registered` | The service never registered | Restart the service and check it logged a successful `PMAPPROC_SET` |
| Service binds to TSAP 111 instead of its real port | Misconfiguration; the service thinks it *is* the portmapper | Fix the startup script |
| Connections accepted but no data flows | `inetd` did not pass the connected FD as FDs 0/1/2 | Check the `wait/nowait` flags in `/etc/inetd.conf` |

## Build It

1. Run `code/main.py`: it boots a tiny portmapper, registers two services (`BitTorrent` -> 6881 and `BackupAgent` -> 45000), answers a `GETPORT` query, and then runs an `inetd` simulation that forks the requested service when a connection arrives.
2. Inspect the registration log: each `PMAPPROC_SET` records `(program, version, proto, port)`.
3. Query the portmapper from the simulated client and verify the response matches the registered port.
4. Inspect the on-demand spawn: when a connection to TSAP 6881 arrives, the `inetd` simulation `fork()`s a child that "inherits" the connection FD. The child prints the file it would serve and exits; the parent goes back to listening.
5. Add a third service to the registry, restart the simulation, and confirm the portmapper returns the new port.
6. Stop the portmapper before the client queries — observe the `ECONNREFUSED` and the fallback behaviour you implement in `client_with_fallback()`.

## Use It

| Task | Real tool | What good looks like |
|---|---|---|
| Find a registered port | `rpcinfo -p` | Lists every program-number -> port mapping the local `rpcbind` knows |
| List all listening sockets | `ss -tulpn` | Shows which process holds each well-known TSAP; the portmapper is at `:111` |
| Trace a portmapper query | `strace -e trace=sendto,recvfrom -f program` | Capture the `PMAPPROC_GETPORT` UDP datagram and the response |
| Run inetd for one service | `systemd-socket-activate -l 9000 --fd=3 ./server` | The socket is held by systemd; the child inherits FD 3 on demand |
| Resolve a service in DNS | `dig +short SRV _sip._tcp.example.com` | Returns `10 5 5060 sip.example.com.` — the well-known port is in the registry |

## Ship It

Produce one reusable artifact under `outputs/`:

- A portmapper service definition in `/etc/rpcbind.conf.d/` (or equivalent) for a custom service, with the `rpcinfo -p` proof that the registration took effect.
- An `inetd.conf` entry (or systemd `.socket` unit) that listens on a custom TSAP and runs a small service on demand. Verify the spawn with `ss -tlnp` and `ps`.
- A troubleshooting runbook mapping the four failure modes in the table above to the commands that fix them.

Start from [`outputs/prompt-tsap-nsap-portmapper-and-initial-connection-protocol.md`](../outputs/prompt-tsap-nsap-portmapper-and-initial-connection-protocol.md).

## Exercises

1. Predict the response to a `PMAPPROC_GETPORT` query for a service the portmapper has not seen. Run the simulation and confirm it returns 0 (the historical "not registered" reply).
2. In the `inetd` simulation, change the child to log FD 0 / FD 1 / FD 2 instead of inheriting the connection. Predict what happens to a service that uses `stdio`. Verify by running.
3. The portmapper uses UDP for control traffic. What happens if a `PMAPPROC_SET` is lost? Design a heartbeat that lets the portmapper garbage-collect dead registrations after T seconds of silence. Implement it in `code/main.py` and test.
4. The well-known TSAP of the portmapper is 111. Why is 111 not a privileged port on some Unix variants? What does that mean for an attacker?
5. Modern service discovery uses DNS SRV. Write a portmapper that returns an `SRV` query result instead of a port number. Compare the round-trip cost: one DNS UDP query vs. one portmapper UDP query.
6. Trace a real NFS mount: `mount.nfs server:/export /mnt`. How many `rpcbind` calls does it make before the first byte of data is on the wire?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| TSAP | "port number" | Transport Service Access Point; in the Internet, a 16-bit TCP or UDP port |
| NSAP | "IP address" | Network Service Access Point; IPv4 (32-bit) or IPv6 (128-bit) |
| Portmapper | "rpcbind" | A well-known service on TSAP 111 that maps `(program, version, protocol)` triples to the TSAP the service actually bound |
| `rpcbind` | "the new portmap" | The Sun RPC successor to BSD's `portmap`; serves the same protocol (RFC 1833) |
| `inetd` | "super-server" | A daemon that listens on many TSAPs and forks the registered service on demand; the modern form is `systemd` socket activation |
| Well-known port | "the standard port" | A port in 0-1023 reserved for privileged services; requires root to bind on Unix |
| Registered port | "the IANA port" | A port in 1024-49151, administratively assigned but not privileged |
| Ephemeral port | "the random port" | A port in 49152-65535 chosen by the kernel for outgoing connections |
| Initial connection protocol | "lazy forking" | The protocol of Figure 6-9: process server listens, forks the service when a connection arrives, passes the FD to the child |
| Service registry | "modern portmap" | A HTTP/JSON service like Consul or etcd; replaces the portmapper for cloud-native systems |

## Further Reading

- RFC 768 — User Datagram Protocol (the transport below the portmapper's control channel)
- RFC 793 — Transmission Control Protocol (the transport below any TCP-based service)
- RFC 1833 — Binding Protocols for ONC RPC Version 2 (the portmapper's wire protocol)
- RFC 4506 — XDR: External Data Representation Standard (the encoding portmapper uses)
- RFC 2782 — A DNS RR for specifying the location of services (DNS SRV, the modern portmap)
- RFC 1236 — TCP/UDP Port Snooping (an early security note on portmapper exposure)
- Stevens, *Unix Network Programming, Volume 2: Interprocess Communications*, 2nd ed. — Ch. 16 (the portmapper)
- `rpcbind(8)`, `rpcinfo(8)`, `inetd(8)`, `systemd.socket(5)` Linux man pages
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed. — Ch. 6 (this lesson is the portmapper portion of 6.2.1)
