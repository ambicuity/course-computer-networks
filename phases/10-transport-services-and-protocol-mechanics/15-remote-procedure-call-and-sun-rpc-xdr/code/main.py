"""Remote Procedure Call: Sun RPC (RFC 5531) + XDR (RFC 4506).

Four stdlib-only parts:

1. xdr module - encode and decode every type in RFC 4506: int, unsigned int,
   hyper, bool, float, double, string, opaque, array. Always big-endian,
   4-byte aligned.

2. RpcCall / RpcReply - build a CALL and a REPLY record with AUTH_UNIX
   credentials. The transaction ID (XID) is 32 bits, the program/version/
   procedure triple is the dispatch key.

3. Record-marked TCP framing - prepend a 4-byte big-endian length whose MSB
   is the "last fragment" bit (1 = last). Splits long messages into chunks.

4. Tiny RPC server - handles procedure 1 = DOUBLE(int) -> int on loopback,
   with a real socket and one client issuing two calls.

Run: python3 main.py
"""

from __future__ import annotations

import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Optional


# --- XDR encode/decode (RFC 4506) ---------------------------------------------
def pad4(n: int) -> int:
    return (4 - (n % 4)) % 4


class XDREncoder:
    def __init__(self) -> None:
        self.buf = bytearray()

    def int(self, v: int) -> "XDREncoder":
        self.buf += struct.pack("!i", v)
        return self

    def uint(self, v: int) -> "XDREncoder":
        self.buf += struct.pack("!I", v)
        return self

    def hyper(self, v: int) -> "XDREncoder":
        self.buf += struct.pack("!q", v)
        return self

    def boolean(self, v: bool) -> "XDREncoder":
        self.buf += struct.pack("!I", 1 if v else 0)
        return self

    def float_(self, v: float) -> "XDREncoder":
        self.buf += struct.pack("!f", v)
        return self

    def double(self, v: float) -> "XDREncoder":
        self.buf += struct.pack("!d", v)
        return self

    def string(self, s: str) -> "XDREncoder":
        b = s.encode("utf-8")
        self.uint(len(b))
        self.buf += b
        self.buf += b"\x00" * pad4(len(b))
        return self

    def opaque(self, b: bytes) -> "XDREncoder":
        self.uint(len(b))
        self.buf += b
        self.buf += b"\x00" * pad4(len(b))
        return self

    def bytes(self) -> bytes:
        return bytes(self.buf)


class XDRDecoder:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def int(self) -> int:
        v = struct.unpack_from("!i", self.data, self.pos)[0]
        self.pos += 4
        return v

    def uint(self) -> int:
        v = struct.unpack_from("!I", self.data, self.pos)[0]
        self.pos += 4
        return v

    def hyper(self) -> int:
        v = struct.unpack_from("!q", self.data, self.pos)[0]
        self.pos += 8
        return v

    def boolean(self) -> bool:
        return self.uint() != 0

    def float_(self) -> float:
        v = struct.unpack_from("!f", self.data, self.pos)[0]
        self.pos += 4
        return v

    def double(self) -> float:
        v = struct.unpack_from("!d", self.data, self.pos)[0]
        self.pos += 8
        return v

    def string(self) -> str:
        n = self.uint()
        s = self.data[self.pos:self.pos + n].decode("utf-8")
        self.pos += n + pad4(n)
        return s

    def opaque(self) -> bytes:
        n = self.uint()
        b = self.data[self.pos:self.pos + n]
        self.pos += n + pad4(n)
        return b


# --- ONC RPC record (RFC 5531) ------------------------------------------------
CALL = 0
REPLY = 1
MSG_ACCEPTED = 0
AUTH_NULL = 0
AUTH_UNIX = 1
SUCCESS = 0
PROG_MISMATCH = 2
PROC_UNAVAIL = 3
GARBAGE_ARGS = 4


def encode_auth_null() -> bytes:
    return XDREncoder().uint(AUTH_NULL).uint(0).bytes()


def encode_auth_unix(stamp: int, mach: str, uid: int, gid: int,
                     gids: list[int]) -> bytes:
    enc = XDREncoder().uint(AUTH_UNIX)
    body = XDREncoder().uint(stamp).string(mach).uint(uid).uint(gid)
    body.uint(len(gids))
    for g in gids:
        body.uint(g)
    body_bytes = body.bytes()
    enc.uint(len(body_bytes))
    return enc.bytes() + body_bytes


def encode_call(xid: int, prog: int, vers: int, proc: int,
                args: bytes, cred: bytes, verf: bytes) -> bytes:
    enc = XDREncoder().uint(xid).uint(CALL).uint(2)
    enc.uint(prog).uint(vers).uint(proc)
    enc.buf += cred
    enc.buf += verf
    enc.buf += args
    return enc.bytes()


def encode_reply(xid: int, accept_stat: int, results: bytes,
                 verf: bytes) -> bytes:
    enc = XDREncoder().uint(xid).uint(REPLY).uint(2)
    enc.uint(MSG_ACCEPTED)
    enc.buf += verf
    enc.uint(accept_stat)
    enc.buf += results
    return enc.bytes()


# --- Record marking (RPC over TCP, RFC 5531 sec 8) ---------------------------
def record_mark(fragments: list[bytes], last: bool = True) -> bytes:
    """Prepend a 4-byte big-endian length to each fragment; mark last."""
    out = bytearray()
    for i, frag in enumerate(fragments):
        is_last = (i == len(fragments) - 1) and last
        flag = 0x80000000 if is_last else 0x00000000
        out += struct.pack("!I", flag | len(frag))
        out += frag
    return bytes(out)


# --- Demo server + client -----------------------------------------------------
def demo_xdr() -> None:
    print("=" * 70)
    print("XDR ROUND-TRIP")
    print("=" * 70)
    enc = (XDREncoder()
           .int(42)
           .int(-1)
           .uint(7)
           .hyper(2 ** 40)
           .float_(3.5)
           .double(2.718281828)
           .boolean(True)
           .string("hello rpc"))
    raw = enc.bytes()
    print(f"  encoded {len(raw)} bytes: {raw.hex()}")
    dec = XDRDecoder(raw)
    print(f"  int={dec.int()}, neg_int={dec.int()}, uint={dec.uint()}, "
          f"hyper={dec.hyper()}, float={dec.float_()}, "
          f"double={dec.double()}, bool={dec.boolean()}, "
          f"string={dec.string()!r}")


def demo_rpc_records() -> None:
    print("\n" + "=" * 70)
    print("RPC CALL + REPLY (RFC 5531)")
    print("=" * 70)
    cred = encode_auth_unix(stamp=int(time.time()), mach="lab",
                            uid=501, gid=20, gids=[20, 80])
    verf = encode_auth_null()
    args = XDREncoder().int(7).bytes()
    call = encode_call(xid=0x12345678, prog=100003, vers=3, proc=1,
                       args=args, cred=cred, verf=verf)
    print(f"  CALL  ({len(call):3d} B) hex: {call.hex()}")
    reply = encode_reply(xid=0x12345678, accept_stat=SUCCESS,
                         results=XDREncoder().int(14).bytes(), verf=verf)
    print(f"  REPLY ({len(reply):3d} B) hex: {reply.hex()}")


def demo_record_marking() -> None:
    print("\n" + "=" * 70)
    print("RECORD MARKING (TCP, 4-byte length with MSB = last)")
    print("=" * 70)
    payload = b"X" * 100
    framed = record_mark([payload[:30], payload[30:60], payload[60:]])
    print(f"  3 fragments of 30+30+10 bytes, framed: {len(framed)} bytes")
    print(f"  first length word = 0x{struct.unpack('!I', framed[:4])[0]:08X} "
          f"(MSB=0 means more follow)")
    print(f"  last length word  = 0x{struct.unpack('!I', framed[-104:-100])[0]:08X} "
          f"(MSB=1 means last fragment)")


def live_rpc() -> None:
    print("\n" + "=" * 70)
    print("LIVE RPC OVER LOOPBACK (procedure 1 = DOUBLE)")
    print("=" * 70)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    addr = srv.getsockname()

    def serve() -> None:
        conn, _ = srv.accept()
        # Read one record-marked call.
        hdr = b""
        while len(hdr) < 4:
            hdr += conn.recv(4 - len(hdr))
        flag_len = struct.unpack("!I", hdr)[0]
        last = bool(flag_len & 0x80000000)
        n = flag_len & 0x7FFFFFFF
        body = b""
        while len(body) < n:
            body += conn.recv(n - len(body))
        # Parse XID, proc, args.
        dec = XDRDecoder(body)
        xid = dec.uint()
        mtype = dec.uint()
        rpcver = dec.uint()
        prog = dec.uint()
        vers = dec.uint()
        proc = dec.uint()
        # Skip cred + verf.
        cf = dec.uint()
        cl = dec.uint()
        dec.pos += cl
        vf = dec.uint()
        vl = dec.uint()
        dec.pos += vl
        arg = dec.int()
        # Reply.
        reply = encode_reply(xid=xid, accept_stat=SUCCESS,
                             results=XDREncoder().int(arg * 2).bytes(),
                             verf=encode_auth_null())
        framed = record_mark([reply])
        conn.sendall(framed)
        print(f"  [SERVER] xid=0x{xid:08x} prog={prog} ver={vers} "
              f"proc={proc} arg={arg} -> {arg * 2} (last={last})")
        conn.close()
        srv.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    time.sleep(0.05)

    cli = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    cli.connect(addr)
    for xid_in, arg in ((0xABCDEF01, 21), (0xABCDEF02, 99)):
        call = encode_call(xid=xid_in, prog=200000, vers=1, proc=1,
                           args=XDREncoder().int(arg).bytes(),
                           cred=encode_auth_null(),
                           verf=encode_auth_null())
        cli.sendall(record_mark([call]))
        hdr = b""
        while len(hdr) < 4:
            hdr += cli.recv(4 - len(hdr))
        n = struct.unpack("!I", hdr)[0] & 0x7FFFFFFF
        body = b""
        while len(body) < n:
            body += cli.recv(n - len(body))
        dec = XDRDecoder(body)
        xid_out = dec.uint()
        mtype = dec.uint()
        rpcver = dec.uint()
        # Skip accept_stat + verf + results code.
        dec.uint()
        vf = dec.uint()
        vl = dec.uint()
        dec.pos += vl
        accept = dec.uint()
        result = dec.int()
        print(f"  [CLIENT] xid=0x{xid_in:08x} arg={arg} -> reply xid=0x{xid_out:08x} "
              f"accept={accept} result={result}")
    cli.close()
    t.join(timeout=1.0)


def main() -> None:
    demo_xdr()
    demo_rpc_records()
    demo_record_marking()
    live_rpc()
    print("\nDone. Edit `live_rpc` to add more procedures or to switch to UDP.")


if __name__ == "__main__":
    main()
