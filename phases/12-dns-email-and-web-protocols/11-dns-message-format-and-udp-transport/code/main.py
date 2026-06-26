#!/usr/bin/env python3
"""DNS message format encoder/decoder (RFC 1035, RFC 6891).

This is an offline, stdlib-only implementation of the DNS wire format used in
the lesson on DNS messages and UDP transport. It packs/unpacks the 12-byte
header, encodes/decodes domain names with length-prefix labels and compression
pointers, builds minimal resource records (A, AAAA, NS, MX, CNAME, TXT, OPT),
and demonstrates an EDNS(0) OPT pseudo-record.

No network calls. Run with `python3 main.py`.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import List, Tuple

PORT = 53
CLASS_IN = 1
MAX_UDP_NO_EDNS = 512

RCODE_NOERROR = 0
RCODE_FORMERR = 1
RCODE_SERVFAIL = 2
RCODE_NXDOMAIN = 3
RCODE_NOTIMP = 4
RCODE_REFUSED = 5

TYPE_A = 1
TYPE_NS = 2
TYPE_CNAME = 5
TYPE_MX = 15
TYPE_TXT = 16
TYPE_AAAA = 28
TYPE_OPT = 41
TYPE_DS = 43
TYPE_RRSIG = 46
TYPE_DNSKEY = 48

POINTER_MASK = 0xC0
POINTER_PREFIX = 0xC0


@dataclass(frozen=True)
class Header:
    qid: int
    qr: int
    opcode: int
    aa: int
    tc: int
    rd: int
    ra: int
    ad: int
    cd: int
    rcode: int
    qdcount: int
    ancount: int
    nscount: int
    arcount: int


def encode_name(name: str) -> bytes:
    """Encode an FQDN as RFC 1035 length-prefixed labels ending in a zero root."""
    if name.endswith("."):
        name = name[:-1]
    if not name:
        return b"\x00"
    out = bytearray()
    for label in name.split("."):
        b = label.encode("ascii")
        if not 0 < len(b) <= 63:
            raise ValueError(f"label {label!r} out of range (1..63 bytes)")
        out.append(len(b))
        out.extend(b)
    out.append(0)
    return bytes(out)


def decode_name(msg: bytes, offset: int) -> Tuple[str, int]:
    """Decode an RFC 1035 name at `offset`, following compression pointers."""
    labels: List[str] = []
    jumped = False
    original_offset = offset
    loops = 0
    while True:
        if offset >= len(msg):
            raise ValueError("name decode ran past end of message")
        length = msg[offset]
        if length == 0:
            offset += 1
            break
        if (length & POINTER_MASK) == POINTER_PREFIX:
            if offset + 2 > len(msg):
                raise ValueError("truncated pointer")
            if not jumped:
                original_offset = offset + 2
            pointer = ((length & 0x3F) << 8) | msg[offset + 1]
            offset = pointer
            jumped = True
        else:
            offset += 1
            if offset + length > len(msg):
                raise ValueError("label overruns message")
            labels.append(msg[offset : offset + length].decode("ascii"))
            offset += length
        loops += 1
        if loops > 64:
            raise ValueError("too many pointer hops (loop?)")
    return ".".join(labels), (original_offset if jumped else offset)


@dataclass
class ResourceRecord:
    name: str
    rtype: int
    rclass: int
    ttl: int
    rdata: bytes
    rdata_text: str = ""

    def pack(self, name_pool: dict[str, int]) -> bytes:
        out = bytearray()
        out.extend(encode_name(self.name))
        out.extend(struct.pack("!HHI", self.rtype, self.rclass, self.ttl))
        rdata = self._render_rdata(name_pool)
        out.extend(struct.pack("!H", len(rdata)))
        out.extend(rdata)
        return bytes(out)

    def _render_rdata(self, name_pool: dict[str, int]) -> bytes:
        if self.rtype == TYPE_A and len(self.rdata) == 4:
            return self.rdata
        if self.rtype == TYPE_AAAA and len(self.rdata) == 16:
            return self.rdata
        if self.rtype in (TYPE_NS, TYPE_CNAME):
            return encode_name(self.rdata_text)
        if self.rtype == TYPE_MX:
            preference = struct.unpack("!H", self.rdata[:2])[0]
            return struct.pack("!H", preference) + encode_name(self.rdata_text)
        if self.rtype == TYPE_TXT:
            payload = self.rdata_text.encode("utf-8")
            if len(payload) > 255:
                raise ValueError("TXT chunk exceeds 255 bytes")
            return bytes([len(payload)]) + payload
        if self.rtype == TYPE_OPT:
            return self.rdata
        return self.rdata


@dataclass
class Message:
    header: Header
    question: Tuple[str, int, int] = ("", 0, 0)
    answer: List[ResourceRecord] = field(default_factory=list)
    authority: List[ResourceRecord] = field(default_factory=list)
    additional: List[ResourceRecord] = field(default_factory=list)

    def pack(self) -> bytes:
        flags = (
            (self.header.qr & 1) << 15
            | (self.header.opcode & 0xF) << 11
            | (self.header.aa & 1) << 10
            | (self.header.tc & 1) << 9
            | (self.header.rd & 1) << 8
            | (self.header.ra & 1) << 7
            | (self.header.ad & 1) << 5
            | (self.header.cd & 1) << 4
            | (self.header.rcode & 0xF)
        )
        out = bytearray()
        out.extend(
            struct.pack(
                "!HHHHHH",
                self.header.qid,
                flags,
                self.header.qdcount,
                self.header.ancount,
                self.header.nscount,
                self.header.arcount,
            )
        )
        qname, qtype, qclass = self.question
        out.extend(encode_name(qname))
        out.extend(struct.pack("!HH", qtype, qclass))
        for rr in self.answer:
            out.extend(rr.pack({}))
        for rr in self.authority:
            out.extend(rr.pack({}))
        for rr in self.additional:
            out.extend(rr.pack({}))
        return bytes(out)


def pack_header(**kwargs) -> bytes:
    defaults = dict(
        qid=0,
        qr=0,
        opcode=0,
        aa=0,
        tc=0,
        rd=0,
        ra=0,
        ad=0,
        cd=0,
        rcode=0,
        qd=0,
        an=0,
        ns=0,
        ar=0,
    )
    defaults.update(kwargs)
    h = Header(**defaults)
    return Message(h).pack()[:12]


def unpack_header(data: bytes) -> Header:
    if len(data) < 12:
        raise ValueError("DNS message shorter than 12-byte header")
    qid, flags, qd, an, ns, ar = struct.unpack("!HHHHHH", data[:12])
    return Header(
        qid=qid,
        qr=(flags >> 15) & 1,
        opcode=(flags >> 11) & 0xF,
        aa=(flags >> 10) & 1,
        tc=(flags >> 9) & 1,
        rd=(flags >> 8) & 1,
        ra=(flags >> 7) & 1,
        ad=(flags >> 5) & 1,
        cd=(flags >> 4) & 1,
        rcode=flags & 0xF,
        qdcount=qd,
        ancount=an,
        nscount=ns,
        arcount=ar,
    )


def build_opt_record(udp_payload: int = 4096, do: bool = True, ad: bool = False) -> ResourceRecord:
    flags = (do << 15) | (ad << 14)
    rdata = struct.pack("!HBBIBI", 0, 0, 0, 0, 0, 0)
    rdata = struct.pack("!HIH", udp_payload, 0, flags) + rdata[8:]
    return ResourceRecord(name="", rtype=TYPE_OPT, rclass=udp_payload, ttl=0, rdata=rdata)


def build_query(name: str, qtype: int, qid: int = 0x1234, use_edns: bool = True) -> Message:
    additional = [build_opt_record()] if use_edns else []
    return Message(
        header=Header(
            qid=qid,
            qr=0,
            opcode=0,
            rd=1,
            qdcount=1,
            ancount=0,
            nscount=0,
            arcount=len(additional),
        ),
        question=(name, qtype, CLASS_IN),
        additional=additional,
    )


def decode_response(data: bytes) -> Tuple[Header, List[ResourceRecord]]:
    h = unpack_header(data)
    rrs: List[ResourceRecord] = []
    offset = 12
    for _ in range(h.qdcount):
        _, offset = decode_name(data, offset)
        offset += 4
    for count in (h.ancount, h.nscount, h.arcount):
        for _ in range(count):
            name, offset = decode_name(data, offset)
            rtype, rclass, ttl, rdlen = struct.unpack("!HHIH", data[offset : offset + 10])
            offset += 10
            rdata = data[offset : offset + rdlen]
            offset += rdlen
            rrs.append(ResourceRecord(name, rtype, rclass, ttl, rdata))
    return h, rrs


SAMPLE_RESPONSE = bytes.fromhex(
    "123481800001000100000000"  # header: ID=0x1234, QR=1 RD=1 RA=1, ANCOUNT=1
    "076578616d706c6503636f6d00"  # QNAME: example.com
    "0001"  # QTYPE = A
    "0001"  # QCLASS = IN
    "c00c"  # pointer to offset 0x0c (QNAME)
    "0001"  # TYPE = A
    "0001"  # CLASS = IN
    "0000012c"  # TTL = 300
    "0004"  # RDLENGTH = 4
    "5db8d822"  # RDATA = 93.184.216.34 (example.com)
)


def main() -> None:
    print("=" * 64)
    print("DNS MESSAGE FORMAT  --  RFC 1035 / RFC 6891")
    print("=" * 64)

    q = build_query("example.com", TYPE_A)
    wire = q.pack()
    print(f"\nquery bytes ({len(wire)} B):")
    print("  " + wire.hex())
    print(f"  ENDS_HERE if longer than {MAX_UDP_NO_EDNS}: {len(wire) > MAX_UDP_NO_EDNS}")

    h = unpack_header(wire)
    print("\nparsed header:")
    print(f"  ID=0x{h.qid:04x}  QR={h.qr}  OPCODE={h.opcode}  AA={h.aa}  TC={h.tc}  "
          f"RD={h.rd}  RA={h.ra}  AD={h.ad}  CD={h.cd}  RCODE={h.rcode}")
    print(f"  QD={h.qdcount}  AN={h.ancount}  NS={h.nscount}  AR={h.arcount}")

    print("\ndecoded sample response:")
    rh, rrs = decode_response(SAMPLE_RESPONSE)
    print(f"  ID=0x{rh.qid:04x}  QR={rh.qr}  RCODE={rh.rcode}  ANCOUNT={rh.ancount}")
    for rr in rrs:
        if rr.rtype == TYPE_A:
            addr = ".".join(str(b) for b in rr.rdata)
            print(f"  {rr.name:30s} A    TTL={rr.ttl}  {addr}")
        elif rr.rtype == TYPE_OPT:
            udp_size = rr.rclass
            print(f"  OPT pseudo-RR  UDP payload={udp_size}  (EDNS(0))")
        else:
            print(f"  {rr.name}  TYPE={rr.rtype}  TTL={rr.ttl}")

    print("\ntransport guidance:")
    print(f"  RFC 1035 UDP cap without EDNS: {MAX_UDP_NO_EDNS} B (truncated -> TC=1, retry TCP)")
    print("  RFC 6891 EDNS(0) advertises UDP buffer in OPT (commonly 1232 or 4096)")
    print("  RFC 7766 mandates TCP fallback for large / signed / AXFR responses")


if __name__ == "__main__":
    main()
