# An Example of Socket Programming: an Internet File Server

> Tanenbaum §6.1.4 walks through a complete, runnable TCP file-transfer program in C: the server binds port 12345, listens with a 10-deep queue, accepts a connection, reads a filename, opens the file, and writes the bytes back in 4096-byte blocks; the client resolves the server's hostname with `gethostbyname`, calls `connect`, writes the filename, and reads the response into stdout until EOF. The example is intentionally bare - one thread, no auth, no integrity check - so the lesson is not the code, it is the dissection: which BSD headers supply which types, why `htonl`/`htons` exist (endianness across a heterogeneous Internet), what `INADDR_ANY` means (a wildcard bind), why `SO_REUSEADDR` is set (so the server can be restarted without waiting for the kernel to free port 12345), and the textbook's own "limitations" list - no threads, no error reporting, no security - that map directly to the hardening steps a real server needs.

**Type:** Build
**Languages:** Python (in-process socket simulator mirroring the C client/server from Fig. 6-6)
**Prerequisites:** Berkeley Sockets (lesson 03), transport service primitives (lesson 02)
**Time:** ~75 minutes

## Learning Objectives

- Read the C source of Fig. 6-6 and place every header, struct, and call against its socket-API role: `sys/socket.h` for the API, `netinet/in.h` for the address family, `netdb.h` for `gethostbyname`, `sys/fcntl.h` for the file-mode flags.
- Trace a single request through the server: `socket -> setsockopt(SO_REUSEADDR) -> bind(0.0.0.0:12345) -> listen(10) -> accept -> read filename -> open(filename) -> loop { read file, write socket } -> close`.
- Trace a single request through the client: `gethostbyname -> socket -> connect -> write filename + NUL -> loop { read socket, write stdout } -> exit`.
- Explain why `htonl`/`htons` and the `sin_*` byte-order calls are necessary: x86 is little-endian, SPARC was big-endian, and the network wire format is big-endian; `htonl` and `ntohl` are no-ops on big-endian machines, identity-shuffles on little-endian ones.
- Identify the five limitations the textbook flags in the program and propose a minimal fix for each (forking, bounds-checked reads, length-prefix framing, chroot or capability-based sandboxing, struct `stat` size check).

## The Problem

You have inherited a 200-line C file server that is "good enough for a textbook, not for production." The original works on a quiet lab network: a client types `client flits.cs.vu.nl /etc/hosts >f` and the file appears on stdout. Then three things go wrong in production:

1. A junior engineer restarts the server while clients are still connected. The next `bind()` returns `EADDRINUSE` and the server dies. The fix is one line - `SO_REUSEADDR` - that the textbook includes for exactly this reason.
2. Two clients connect simultaneously. The first blocks the server's `read()`; the second waits in the kernel's accept queue. Throughput drops to 1 request per file-read. The fix is `fork()` (or `pthread_create`) per accepted connection.
3. A client sends a filename longer than `BUF_SIZE` (4096) and the read either truncates or overruns. The fix is length-prefix framing on the wire.

Understanding the textbook's program is the prerequisite to understanding the production fixes. Every field in `struct sockaddr_in`, every constant, every header exists for a specific reason - the lesson is to name the reason for each one.

## The Concept

Tanenbaum presents the program in two halves: the client (Fig. 6-6, page 504) and the server (Fig. 6-6, page 505). The C code is small enough to read in five minutes; the surrounding concepts (byte order, address binding, sequential vs concurrent service) are what survive a second reading.

### The five headers and why each one exists

| Header | What it provides | Example in Fig. 6-6 |
|---|---|---|
| `<sys/types.h>` | POSIX base types (`size_t`, `ssize_t`, `pid_t`) | implicit in every declaration |
| `<sys/socket.h>` | The socket API - `socket()`, `bind()`, `connect()`, `send()`, `recv()`, `accept()`, `socketaddr`, `socklen_t` | `socket()`, `bind()`, `connect()`, `write()` |
| `<netinet/in.h>` | `struct sockaddr_in`, `INADDR_ANY`, `htonl`, `htons`, `INADDR_ANY` | `channel.sin_family`, `channel.sin_port`, `htonl(INADDR_ANY)` |
| `<netdb.h>` | `struct hostent`, `gethostbyname()` | `h = gethostbyname(argv[1])` |
| `<sys/fcntl.h>` | File-mode flags (`O_RDONLY`) and the `open()` prototype | `fd = open(buf, O_RDONLY)` |

A sixth, `<unistd.h>` for `read`, `write`, and `close`, is needed but the textbook elides it for space; modern C code includes it explicitly.

### The wire address: `struct sockaddr_in` and byte order

The server builds an IPv4 address in a `struct sockaddr_in`:

```c
struct sockaddr_in channel;           /* holds IP address + port */
memset(&channel, 0, sizeof(channel)); /* zero it - C does not init structs */
channel.sin_family = AF_INET;         /* IPv4 (vs AF_INET6 for v6) */
channel.sin_addr.s_addr = htonl(INADDR_ANY); /* wildcard: any local interface */
channel.sin_port   = htons(SERVER_PORT);     /* 12345, in network order */
```

`INADDR_ANY` is the constant `0.0.0.0` - bind to every IPv4 interface. This is what every well-known service does; the alternative is to bind to a specific address, in which case the server is reachable only via that interface. The `htonl` / `htons` calls (host-to-network long / host-to-network short) shuffle the bits to **big-endian** order, which is the network's wire format. A SPARC reading this code does nothing; an x86 swaps bytes. Without these calls, a 32-bit integer that prints as `12345` on the server would arrive as a different 32-bit integer at a peer of the opposite endianness.

### `SO_REUSEADDR` - the one-line restart fix

The textbook's `setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on))` call does one thing: it tells the kernel "if the port is in TIME_WAIT, let me bind it anyway." Without it, a server that crashes or is `Ctrl-C`'d leaves a half-open TCP state in the kernel for 30-120 seconds. Restarting within that window fails with `EADDRINUSE`. With `SO_REUSEADDR`, the new server can rebind immediately. (Note: this is the textbook's defense, not modern best practice. Production servers on Linux additionally tune `tcp_tw_reuse`, on BSD they accept the wait, and on busy services they use a separate load balancer so restart is decoupled from the listen socket.)

### `gethostbyname` and the DNS round-trip

The client's first act is `h = gethostbyname(argv[1])`. This is a synchronous, blocking DNS lookup. On a healthy network it returns in 1-20 ms; on a broken one it can hang for the resolver's timeout (often 5 seconds per attempt, two attempts, so 10 seconds) and then fail. Modern code uses `getaddrinfo` (which is IPv6-aware and thread-safe), but `gethostbyname` is what the textbook shows, and it is what `strace` will reveal as a `connect(2)` to port 53 (or `/etc/hosts` read) followed by a `recvfrom`. The result is a `struct hostent` whose `h_addr` field is the 4-byte IPv4 address, which the textbook copies into the sockaddr with `memcpy(&channel.sin_addr.s_addr, h->h_addr, h->h_length)`.

### The server's main loop and the `read/write` dance

After `accept` returns a new socket `sa`, the server reads the filename: `read(sa, buf, BUF_SIZE)`. The textbook assumes the filename is a NUL-terminated string sent by the client, and that it fits in `BUF_SIZE`. Both assumptions are technically wrong (the wire is a byte stream, not a record stream, and the client might send a long path), but they are the kind of simplification that 200-line programs tolerate.

The server then `open()`s the file and loops `read(fd) -> write(sa)` until `read` returns 0 (EOF). It `close(fd)`s the file and `close(sa)`s the connection, then loops back to `accept`. The server thread stays in this loop forever; the only way to stop it is a signal.

### The client's main loop and stdout

The client `write()`s the filename plus a trailing NUL byte (so the server can `read` until NUL, even though the textbook does not do that explicitly - the trailing NUL is a convention the server relies on to delimit the filename). Then it enters `while (1) { bytes = read(s, buf, BUF_SIZE); if (bytes <= 0) exit(0); write(1, buf, bytes); }`. The `1` in `write(1, ...)` is the POSIX constant `STDOUT_FILENO`; the textbook hard-codes `1` for brevity. `exit(0)` on `bytes <= 0` is the EOF signal: the server's `close(sa)` translated to a FIN, which `read` reports as zero bytes.

### The five limitations and their minimal fixes

| Limitation (textbook) | Minimal fix | Why it matters |
|---|---|---|
| Error checking is meager | Check every return value; use `perror()` or `strerror(errno)` | One missed check is one silent failure that surfaces at the worst time |
| Error reporting is mediocre | Replace `fatal()` with a logging function that includes `errno`, the function name, and the local peer's address | "Connection refused" with no peer is useless; "connect to 10.0.1.5:80 failed: ECONNREFUSED" is debuggable |
| Single-threaded | Wrap the post-`accept` work in `fork()` (or `pthread_create()`) | Sequential service means a 30-second file blocks every other client |
| Filename fits in `BUF_SIZE` (no bound) | Send a 2-byte length prefix before the filename, and `read` exactly that many bytes | Without this, a malicious client can send 4096 bytes of filename and the server will overflow its buffer on the next read |
| No security (runs as root, no chroot, no caps) | Run as a non-privileged user, chroot into the served directory, drop capabilities | The textbook server can read any file the process can reach; that is `/etc/shadow` if it runs as root |

## Build It

`code/main.py` reimplements the C client and server in pure Python with an in-process socket simulator. The structure mirrors Fig. 6-6:

1. **Server setup** - `socket -> bind(0.0.0.0:12345) -> setsockopt(SO_REUSEADDR) -> listen(10)`, then loop `accept -> read filename -> open(filename) -> loop { read file, write socket } -> close`.
2. **Client setup** - `gethostbyname -> socket -> connect -> write filename + NUL`.
3. **Transfer** - server reads the file in `BUF_SIZE = 4096` chunks; client reads in `BUF_SIZE` chunks until EOF.
4. **EOF signaling** - the server's `close(sa)` becomes a zero-byte `recv` on the client, which exits.
5. **Limitations probe** - a separate scenario shows what happens when the requested file does not exist (`fatal("open failed")` in the textbook, surfaced as an exception in the simulator).

Run with `python3 code/main.py`. The state transitions, byte counts, and chunk boundaries print to the terminal so you can compare them against the C code line-by-line.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Map a C struct to a Python call | `struct sockaddr_in` vs `(host, port)` tuple | Every field in the C struct has an equivalent in the Python simulator's wire format |
| Predict chunk boundaries | number of `SEND` calls vs number of `RECV` calls | The simulator's 4096-byte boundary matches the textbook's `BUF_SIZE` |
| Distinguish `accept`'s return value | original socket vs new socket | Server continues to `accept` on the listening socket; the new one is for I/O |
| Diagnose "file not found" | exception thrown by `open()` | Surfaces in the simulator's log as the file-server fatal-equivalent |
| Verify EOF signaling | `recv() == 0` on the client | One `read(0)` per `close()`; this is the FIN translation |
| Test `SO_REUSEADDR` behavior | rebind immediately after a close | The simulator allows rebinding to the same port while a prior connection is in TIME_WAIT |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **C-to-Python porting checklist** that walks Fig. 6-6 line by line and matches each `socket()` / `bind()` / `accept()` call against its simulator equivalent.
- A **five-limitations fix plan** with code stubs for `fork()`-per-connection, length-prefix framing, errno-rich logging, and chroot drop.
- A **`SO_REUSEADDR` decision matrix** showing when to use it, when to wait for TIME_WAIT, and when to put a load balancer in front.

Start from `outputs/prompt-internet-file-server.md`.

## Exercises

1. A `struct sockaddr_in` has `sin_family = AF_INET` and `sin_port = htons(12345)`. What are the actual bytes of `sin_port` on an x86 machine? On a SPARC? Why does it not matter as long as the host matches the network order?
2. The textbook's server calls `setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on))`. The `on` variable is `int on = 1`. What value does the kernel see in the `optval` pointer? What happens if you pass `on = 0`?
3. The client writes `argv[2]` (the filename) followed by `strlen(argv[2]) + 1` bytes. The extra byte is the NUL terminator. What does the server's `read(sa, buf, BUF_SIZE)` actually receive? If the client wrote 100 bytes and the server's buffer is 4096, what does the server's read return?
4. The textbook's server is single-threaded. If client A requests a 10 GB file and client B connects 1 ms later, how long does B wait? What is the simplest fix that the textbook itself recommends in the "limitations" list?
5. The textbook's `fatal()` function prints the message and calls `exit(1)`. The server is bound to port 12345; after `fatal("bind failed")`, can the next `bind` succeed without `SO_REUSEADDR`? Why or why not?
6. Modify `code/main.py` to enforce the length-prefix framing fix from the limitations table. Send a 4-byte big-endian length, then that many bytes of filename. What is the smallest change to the client and the server?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| `struct sockaddr_in` | "the IP address struct" | The C struct holding `(family, port, IPv4 address, padding)`; 16 bytes total, used as a generic `struct sockaddr` cast |
| `INADDR_ANY` | "0.0.0.0" | Wildcard bind - listen on every local interface, not just one |
| `htonl` / `htons` | "byte swap" | host-to-network order; big-endian on the wire regardless of CPU endianness |
| `SO_REUSEADDR` | "allow port reuse" | Lets `bind()` succeed while the port is in TIME_WAIT, so servers can restart fast |
| `gethostbyname` | "DNS lookup" | A blocking, IPv4-only, non-reentrant resolver call; superseded by `getaddrinfo` in modern code |
| `BUF_SIZE = 4096` | "the read size" | A balance: large enough to amortize syscall cost, small enough to fit in a TCP segment (MSS) |
| EOF on `read() == 0` | "the connection closed" | The peer sent a FIN; the kernel drained the receive buffer and `read` returns 0 with no error |
| TIME_WAIT | "we just closed" | A 2 * MSL wait (60 s) after active close; without `SO_REUSEADDR`, no new socket can take the same 4-tuple |

## Further Reading

- **Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §6.1.4** - the source chapter for this lesson (Fig. 6-6, both pages).
- **Stevens, W. R. (1998), *UNIX Network Programming, Volume 1* (3rd ed.), chapters 3-5** - the textbook Stevens's chapter on `socket`, `connect`, and elementary TCP programming.
- **RFC 793** (1981), "Transmission Control Protocol," §3.2 - the FIN handshake, TIME_WAIT, and the connection state diagram.
- **Stevens, *TCP/IP Illustrated, Volume 1* (2nd ed.), §18 - "TCP Connection Establishment and Termination"** - the 3-way handshake and the FIN exchange explained at packet level.
- **`man 2 socket`, `man 7 ip`, `man 2 bind`, `man 2 listen`, `man 2 accept`, `man 3 gethostbyname`** - the canonical C reference for every call in Fig. 6-6.
- **Donahoo, M. & Calvert, K. (2008), *TCP/IP Sockets in C* (2nd ed.), chapters 2-4** - a compact C walkthrough of the same patterns.
