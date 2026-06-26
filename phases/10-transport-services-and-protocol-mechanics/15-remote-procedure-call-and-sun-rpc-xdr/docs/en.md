# Remote Procedure Call: Sun RPC and XDR Encoding

> Remote Procedure Call (RPC) makes a network call look like a local function call. The idea is older than TCP (RFC 707, 1976) but was made practical by Birrell and Nelson's 1984 paper, which introduced *stubs* on both sides to hide the marshaling. Sun Microsystems, building on that work, designed the **Sun RPC** protocol (RFC 1050, 1988; updated RFC 5531, 2009) for **NFS** (RFC 1094, then 1813, then 7530) and **NIS** (the Yellow Pages). Sun RPC pairs the wire protocol with **XDR (External Data Representation)**, RFC 4506, a big-endian, fixed-size, type-driven encoding that lets a SPARC server and a little-endian x86 client exchange integers, floats, strings, and opaque byte arrays without ever knowing about each other's native byte order. The combined RPC/XDR design is still in production today: every NFS v2/v3 packet and every modern Kubernetes API server's gRPC stream uses the same conceptual pattern — opaque record-marked framing on top of TCP, transaction ID for matching calls to replies, and a versioned IDL. This lesson walks the protocol, decodes a real ONC RPC record, implements an XDR encoder/decoder in stdlib Python, and shows how `rpcbind` and `mountd` use these primitives.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 10 lesson 14 (UDP) and lesson 17 (TCP service model); familiarity with byte order and primitive data types
**Time:** ~80 minutes

## Learning Objectives

- Lay out the **ONC RPC record** (transaction ID, direction, RPC version, program, version, procedure, credentials, verifier) field by field, with the exact 4-byte alignment rule.
- Encode and decode the **XDR type system** — int, unsigned int, hyper, float, double, string, opaque, array — and produce a hex string that round-trips through a different byte order.
- Distinguish the **record-marked stream** framing (4-byte length prefix, MSB bit reserved) used by TCP transport from the **single-datagram** framing used by UDP transport.
- Trace a complete RPC call from `clnt_call` to `svc_dispatch`: stub marshals args with XDR, kernel sends, server's stub unmarshals, dispatches, marshals reply, client unmarshals, returns.
- Implement a small RPC server (handles one procedure, returns one integer) and a matching client (calls it twice and verifies the transaction ID and reply match).

## The Problem

A junior engineer is trying to make a Python service call a function on a legacy C application over the network. They write raw TCP, send the integer `42` packed as little-endian, and the C server rejects every packet. The C server is on a SPARC; SPARC is big-endian. The Python code is on x86; x86 is little-endian. The integer is just an integer, but the bytes on the wire are not the same. The same problem happens with floats (IEEE 754 is fine, but the order of the bytes within the 8-byte double is not), with strings (length prefix in big-endian, but the bytes themselves are opaque), and with structs (no padding convention shared between compilers). The XDR spec is the answer: it defines one way to encode every type, and every implementation uses the same.

The junior engineer also notices that the first byte of the C server's response is sometimes `0x80`. That is the *record-marked* flag: when RPC runs over TCP, every record starts with a 4-byte big-endian length whose MSB is the "last fragment" bit (1 = this is the last record in a sequence). The same RPC call over UDP has no length prefix at all — UDP's datagram length *is* the record length.

## The Concept

Sun RPC and XDR are two layers. RPC is the *protocol* (how do we identify a call, match it to a reply, authenticate it). XDR is the *encoding* (how do we put a typed value on the wire). The SVG shows the record layout and the XDR type table; `code/main.py` implements both.

### The ONC RPC record (RFC 5531)

Every RPC call and reply has the same 16-byte fixed header:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                  Transaction ID (XID)                          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|       Message Type            |       RPC Version (2)          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Program Number                              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Program Version                             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Procedure Number                            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Credentials (flavor, length, body...)        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Verifier (flavor, length, body...)           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Call body (XDR-encoded args)                |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| Field | Size | Notes |
|---|---|---|
| XID | 32 bits | Client-chosen; the reply's XID matches the call's |
| Message Type | 32 bits | 0 = CALL, 1 = REPLY |
| RPC Version | 32 bits | Currently 2 |
| Program | 32 bits | e.g. 100003 = NFS, 100005 = mountd, 100000 = portmapper |
| Program Version | 32 bits | e.g. 3 = NFSv3 |
| Procedure | 32 bits | e.g. 1 = GETATTR, 6 = READ, 8 = WRITE in NFSv3 |
| Credentials | variable | Authentication (AUTH_UNIX = 1, AUTH_NULL = 0, AUTH_DES = 3, AUTH_GSS = 6) |
| Verifier | variable | Per-reply authentication (often AUTH_NULL) |
| Body | variable | XDR-encoded call/reply-specific data |

The *server* uses the (program, version, procedure) triple to dispatch. The *client* uses the XID to match replies to outstanding calls — important because RPC over UDP is async, and a slow reply may arrive after the client has issued a new call.

### The TCP record-marking protocol

When RPC runs over TCP, each *fragment* is a 4-byte big-endian length prefix whose MSB is the "last fragment" bit. A long message is split into multiple 4-byte-prefixed fragments; the last one has the MSB set. RFC 5531 §8 calls this "record marking (RM)." UDP RPC has no length prefix at all; the UDP datagram *is* the record. The first byte of a TCP RPC stream may be `0x80 00 00 1C 00 00 00 00 ...` for a 28-byte record (last fragment) — that `0x80` is the high bit, not part of the length.

### XDR (RFC 4506): the encoding

XDR is a typed, big-endian, 4-byte-aligned encoding. Every primitive has a fixed size; every variable-length type is a 4-byte count followed by the data, padded to a 4-byte boundary.

| XDR type | Wire size | Encoding |
|---|---|---|
| int / unsigned int | 4 bytes | big-endian 2's complement or unsigned |
| hyper / unsigned hyper | 8 bytes | big-endian 64-bit |
| bool | 4 bytes | 0x00000000 or 0x00000001 |
| float | 4 bytes | IEEE 754 single, big-endian |
| double | 8 bytes | IEEE 754 double, big-endian |
| enum | 4 bytes | int |
| string | 4 + N bytes | 4-byte length, then bytes, then zero pad to 4-byte boundary |
| opaque | N bytes | Caller pads; the wire format may include a 4-byte length for variable opaque |
| array | 4 + N*size bytes | 4-byte count, then N elements, each padded to 4-byte boundary |
| struct | sum of fields | concatenated field encodings |
| discriminated union | 4 + branch bytes | 4-byte discriminant, then branch encoding |

The rules that make XDR portable:

1. **Big-endian, no padding within a 4-byte slot.** A 4-byte field is exactly 4 bytes.
2. **Strings and variable opaque use a 4-byte length prefix.**
3. **Padding to 4 bytes** at the end of strings and variable-length arrays, by appending zero bytes.
4. **Floats are IEEE 754.** SPARC and x86 agree on the format; the only difference is the byte order of the bytes *within* the 4-byte float. XDR's big-endian rule resolves that.

### Stub generation and IDL

The original Sun RPC used a language called **rpcgen** to read an `.x` file (XDR IDL) and produce C client/server stubs. A simple example:

```c
/* add.x */
const ADD = 1;
const VERSION = 1;

program ADD_PROG {
    version ADD_VERS {
        int ADD(int, int) = 1;
    } = VERSION;
} = ADD;
```

`rpcgen add.x` produces `add.h`, `add_clnt.c`, `add_svc.c`, and `add_xdr.c`. The stubs marshal/unmarshal XDR, handle authentication, and let the application programmer write code that looks like a local function call. Modern analogues: gRPC + Protobuf, Apache Thrift, JSON-RPC, Cap'n Proto. The conceptual shape is identical: IDL → stub generator → marshaled bytes over TCP or UDP.

### The `rpcbind` / `portmapper` problem

A client that wants to call NFSv3 GETATTR does not know which TCP port the NFS server is listening on. It calls program 100000 (portmapper), procedure 4 (PMAPPROC_GETPORT), with arguments (program, version, protocol, port). The portmapper returns the port number; the client then opens a TCP connection to that port. This indirection lets the NFS server pick a port at boot, lets clients discover it, and makes the *program number* the canonical identifier. Modern NFSv4 (RFC 7530) drops this hop by listening on the well-known port 2049.

### Why ONC RPC is still in production

The *encoding* (XDR) is verbose by today's standards — every integer is 4 bytes, every string starts with a 4-byte length — but it is also self-describing at the type level: you can write a decoder from the type description alone, with no schema negotiation. The *protocol* (ONC RPC) is similarly simple, which is why a 30-year-old C server can talk to a 2026 Python client. That durability is the point: the same pattern of typed stubs + length-prefixed records + transaction IDs shows up in gRPC (HTTP/2 + Protobuf), Cap'n Proto, Apache Avro RPC, and every modern microservice framework.

## Build It

`code/main.py` is a stdlib-only RPC + XDR toolkit with four parts.

1. **`xdr` module** — encode and decode `int`, `unsigned_int`, `hyper`, `float`, `double`, `bool`, `string`, `opaque_fixed`, `opaque_variable`, and `array`. Round-trip a complex struct on x86 and verify the bytes are big-endian.
2. **`RpcCall` / `RpcReply`** — build a CALL record and a REPLY record using XDR, including AUTH_UNIX credentials and AUTH_NULL verifier.
3. **Record-marked TCP framing** — prepend the 4-byte length with the "last fragment" bit set; split a long call into two records.
4. **Tiny RPC over loopback** — a real socket-based server that handles procedure 1 (returns the double of its input) and a client that issues two calls and matches the XIDs.

Run `python3 code/main.py`. The demo prints the hex of every record so you can compare against Wireshark's `rpc` dissector.

## Use It

| Task | Evidence | What good looks like |
|---|---|---|
| Decode an XDR int | Hex bytes | First 4 bytes are the integer, big-endian |
| Decode a string | 4-byte length + bytes + pad | "hello" -> `00 00 00 05 68 65 6c 6c 6f 00 00 00` |
| Spot record marking | First 4 bytes of a TCP RPC frame | Length is `0x80000000 | actual_len` (MSB set on last fragment) |
| Match XIDs | Reply XID == Call XID | Client correctly correlates a delayed reply to the right call |
| Round-trip a struct | Build on x86, decode on... well, decode on x86 in big-endian | Bytes are identical regardless of host byte order |

`tshark -V -i lo0 -d tcp.port==2049,rpc` will dissect live NFS packets. Match its output against the demo's hex dump.

## Ship It

Produce one reusable artifact under `outputs/`:

- An **RPC record cheat sheet** with the 8-field header, the TCP record-marking rule, and the XID flow.
- An **XDR type table** with sizes and encodings for every type a working protocol is likely to need.
- A **stub-gen walkthrough**: a 10-line `.x` file and the equivalent Python stubs you would write by hand.
- The **lab code** (`code/main.py`) wired to your own server.

Start from `outputs/prompt-remote-procedure-call-and-sun-rpc-xdr.md`.

## Exercises

1. Encode the integer `42` in XDR and the integer `-1`. Show the bytes. Then encode the string `"rpc"` and the float `3.14`. Why does the float look the way it does?
2. Build a CALL record for `(program=100003, version=3, procedure=1, xid=0x12345678)` with AUTH_UNIX credentials for uid 501, gid 20. What is the total length? What does the verifier look like?
3. Receive the CALL record from exercise 2. Match the XID. Reply with the GETATTR result `(file_type=2, mode=0644, nlink=1)`. What is the wire format?
4. Implement a server that handles procedure `ECHO_BYTES(opaque) -> opaque`. The server returns the input unchanged. Test with an 8-byte input and a 9-byte input. Why does the 9-byte case need padding?
5. Run a `tcpdump` capture of the loopback RPC. Identify the record-marked length prefix, the XID, the program, and the procedure. Match them against the demo's hex output.
6. Implement a discriminated union: `result = { 0: OK(value), 1: ERR(string) }`. Encode one of each and verify the receiver can tell which branch is which.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| RPC | "a network function call" | A pattern where marshaling stubs hide the network; client and server agree on an IDL |
| ONC RPC | "Sun RPC" | The original BSD/Sun RPC protocol (RFC 1050 / RFC 5531); used by NFS, NIS, mountd |
| XDR | "the wire format" | External Data Representation (RFC 4506): big-endian, 4-byte-aligned, type-driven encoding |
| XID | "the transaction id" | A 32-bit client-chosen tag that matches a call to its reply |
| Stubs | "the glue" | Generated code on each side that marshals/unmarshals; the user writes the function body |
| IDL | "the contract" | Interface Description Language: rpcgen's `.x` files, Protobuf `.proto`, Thrift `.thrift` |
| Portmapper / rpcbind | "where is the service" | Program 100000: maps (program, version, protocol) to a TCP/UDP port |
| Record marking | "the 4-byte prefix" | 4-byte big-endian length with MSB = last fragment; used by RPC over TCP |
| AUTH_UNIX | "UID/GID auth" | Credentials carrying the Unix uid, gid, and gids list |
| AUTH_NULL | "no auth" | Zero-length credentials; the common case when the network is trusted |
| NFS | "Network File System" | The canonical Sun RPC application; current version NFSv4.2 (RFC 7862+) |

## Further Reading

- **RFC 4506** — *XDR: External Data Representation Standard* (Srinivasan, 2006), the encoding spec.
- **RFC 5531** — *RPC: Remote Procedure Call Protocol Specification Version 2* (Thurlow, 2009), the modern ONC RPC spec.
- **RFC 1050** — *RPC: Remote Procedure Call Protocol Specification* (Sun Microsystems, 1988), the original.
- **RFC 1014** — *XDR: External Data Representation Standard* (Sun Microsystems, 1987), the original.
- **RFC 7530** — *Network File System (NFS) Version 4 Protocol* (Haynes, Noveck, 2015), the current NFS spec (replaces the NFSv3 portmapper model).
- **RFC 1094** — *NFS: Network File System Protocol Specification* (Sandberg et al., 1989), the original NFS.
- Birrell & Nelson, "Implementing Remote Procedure Calls," *ACM TOCS* 2(1), 1984 — the paper that started the field.
- Stevens, *UNIX Network Programming* (3rd ed.) vol. 2, ch. 16-18 — the practical RPC programming reference.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §6.8 "RPC" — the textbook treatment.
