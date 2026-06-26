"""DNS resolution path tracer (stdlib-only, no network access).

Models what `dig +trace example.com` actually does: start at the root hints,
walk root -> TLD -> authoritative, decoding each DNS message by hand. Includes a
minimal RFC 1035 message parser (header flags, question, RR rdata) and an
iterative resolver that follows NS delegations, mirroring the +trace output a
network engineer reads when debugging a lame delegation or a glue mismatch.

Run:  python3 main.py
"""

from __future__ import annotations

import random
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# --- RFC 1035 header constants ------------------------------------------------
# DNS header is 12 bytes: id(2) flags(2) qd/an/ns/ar counts (2 each).
HEADER_FMT = ">HHHHHH"
TYPE_A = 1
TYPE_NS = 2
TYPE_AAAA = 28
CLASS_IN = 1


@dataclass
class Question:
    qname: str
    qtype: int
    qclass: int

    def to_wire(self) -> bytes:
        out = b"".join(
            bytes([len(label)]) + label.encode() for label in self.qname.split(".") if label
        )
        out += b"\x00"
        out += struct.pack(">HH", self.qtype, self.qclass)
        return out


@dataclass
class ResourceRecord:
    name: str
    rtype: int
    rclass: int
    ttl: int
    rdata: str  # human-readable rdata
    raw_rdata_len: int = 0


@dataclass
class DNSMessage:
    id: int
    flags: int
    question: Optional[Question] = None
    answers: List[ResourceRecord] = field(default_factory=list)
    authority: List[ResourceRecord] = field(default_factory=list)
    additional: List[ResourceRecord] = field(default_factory=list)

    @property
    def rcode(self) -> int:
        return self.flags & 0x000F

    def to_wire(self) -> bytes:
        body = b""
        if self.question:
            body += self.question.to_wire()
        for section in (self.answers, self.authority, self.additional):
            for rr in section:
                body += _encode_name(rr.name)
                body += struct.pack(">HHIH", rr.rtype, rr.rclass, rr.ttl, rr.raw_rdata_len)
                body += _encode_rdata(rr.rdata, rr.rtype, rr.raw_rdata_len)
        return struct.pack(
            HEADER_FMT,
            self.id,
            self.flags,
            1 if self.question else 0,
            len(self.answers),
            len(self.authority),
            len(self.additional),
        ) + body


def _encode_name(name: str) -> bytes:
    if not name or name == ".":
        return b"\x00"
    out = b"".join(bytes([len(lbl)]) + lbl.encode() for lbl in name.split(".") if lbl)
    return out + b"\x00"


def _encode_rdata(rdata: str, rtype: int, length: int) -> bytes:
    if rtype == TYPE_A:
        return bytes(int(p) for p in rdata.split("."))
    if rtype == TYPE_NS:
        return _encode_name(rdata)
    if rtype == TYPE_AAAA:
        return bytes(int(p, 16) for p in rdata.split(":"))
    return rdata.encode()[:length]


def parse_header(wire: bytes) -> Tuple[int, int, int, int, int, int]:
    if len(wire) < 12:
        raise ValueError("truncated DNS header (<12 bytes)")
    return struct.unpack(HEADER_FMT, wire[:12])  # type: ignore[return-value]


def flags_str(flags: int) -> str:
    qr = "qr" if flags & 0x8000 else "qr=0"
    rd = "rd" if flags & 0x0100 else ""
    ra = "ra" if flags & 0x0080 else ""
    aa = "aa" if flags & 0x0400 else ""
    tc = "tc" if flags & 0x0200 else ""
    rcode = flags & 0x000F
    return ",".join(f for f in (qr, aa, tc, rd, ra) if f) + f" rcode={rcode}"


# --- Authoritative server model ----------------------------------------------
# Each server owns exactly one zone. For a query it either answers (name is in
# its zone and it holds the record), refers (name is below a delegated child), or
# returns NXDOMAIN. This is the decision an iterative resolver makes each hop.

@dataclass
class Zone:
    origin: str  # e.g. ".", "com.", "example.com."
    records: List[ResourceRecord]
    # child delegations: child origin -> list of NS names
    delegations: Dict[str, List[str]] = field(default_factory=dict)
    # glue A records for in-zone NS names
    glue: Dict[str, str] = field(default_factory=dict)


@dataclass
class AuthoritativeServer:
    name: str
    zone: Zone

    def answer(self, q: Question) -> DNSMessage:
        qname = q.qname
        # Is qname in or below this zone?
        if not _in_or_below(qname, self.zone.origin):
            return DNSMessage(id=0, flags=0x8000 | 0x0003, question=q)  # NXDOMAIN

        # Is qname below a delegated child? -> referral (no AA, no answer).
        for child_origin, ns_names in self.zone.delegations.items():
            if qname == child_origin or qname.endswith("." + child_origin):
                auth = [ResourceRecord(child_origin, TYPE_NS, CLASS_IN, 172800, ns, 6) for ns in ns_names]
                addl = []
                for ns in ns_names:
                    if ns in self.zone.glue:
                        addl.append(ResourceRecord(ns, TYPE_A, CLASS_IN, 172800, self.zone.glue[ns], 4))
                return DNSMessage(id=0, flags=0x8000, question=q, authority=auth, additional=addl)

        # Otherwise we are authoritative: answer from our own records.
        ans = [rr for rr in self.zone.records if rr.name == qname and rr.rtype == q.qtype]
        flags = 0x8000 | 0x0400  # response + AA
        return DNSMessage(id=0, flags=flags, question=q, answers=ans)


def _in_or_below(qname: str, origin: str) -> bool:
    if origin == ".":
        return True
    return qname == origin or qname.endswith("." + origin)


# --- The zone database: root -> com. -> example.com. -------------------------
ROOT = Zone(
    origin=".",
    records=[],
    delegations={"com.": ["a.gtld-servers.net", "b.gtld-servers.net"]},
    glue={},  # root has no in-zone glue for the gtld names (out-of-bailiwick, cached)
)

COM = Zone(
    origin="com.",
    records=[],
    delegations={"example.com.": ["ns1.example.com", "ns2.example.com"]},
    glue={"ns1.example.com": "192.0.2.53", "ns2.example.com": "192.0.2.54"},
)

EXAMPLE_COM = Zone(
    origin="example.com.",
    records=[
        ResourceRecord("www.example.com.", TYPE_A, CLASS_IN, 300, "93.184.216.34", 4),
        ResourceRecord("example.com.", TYPE_NS, CLASS_IN, 86400, "ns1.example.com", 6),
        ResourceRecord("ns1.example.com.", TYPE_A, CLASS_IN, 172800, "192.0.2.53", 4),
        ResourceRecord("ns2.example.com.", TYPE_A, CLASS_IN, 172800, "192.0.2.54", 4),
    ],
    delegations={},
    glue={},
)

SERVERS: Dict[str, AuthoritativeServer] = {
    "a.root-servers.net": AuthoritativeServer("a.root-servers.net", ROOT),
    "a.gtld-servers.net": AuthoritativeServer("a.gtld-servers.net", COM),
    "ns1.example.com": AuthoritativeServer("ns1.example.com", EXAMPLE_COM),
    "ns2.example.com": AuthoritativeServer("ns2.example.com", EXAMPLE_COM),
}


# --- Iterative resolver (the +trace walk) -------------------------------------
def resolve(qname: str, qtype: int = TYPE_A) -> List[Tuple[str, DNSMessage]]:
    """Walk root -> TLD -> authoritative, returning (server, response) hops."""
    path: List[Tuple[str, DNSMessage]] = []
    qid = random.randint(0, 0xFFFF)
    question = Question(qname, qtype, CLASS_IN)

    # Start at a root server (the resolver's built-in root hints).
    current_server = "a.root-servers.net"
    for _ in range(4):  # root, tld, auth, (one extra safety hop)
        server = SERVERS[current_server]
        resp = server.answer(question)
        resp.id = qid
        path.append((current_server, resp))
        # Follow a referral: pick the first NS, prefer one with glue.
        next_server = None
        for ns_rr in resp.authority:
            for addl in resp.additional:
                if addl.name == ns_rr.rdata and addl.rtype == TYPE_A:
                    next_server = ns_rr.rdata
                    break
            if next_server:
                break
            # no glue: pick by name if it maps to a known server
            if ns_rr.rdata in SERVERS:
                next_server = ns_rr.rdata
                break
        if not next_server or resp.answers:
            break  # got a final answer or ran out of delegations
        current_server = next_server
    return path


def print_trace(qname: str) -> None:
    print(f";; +trace resolving {qname} A\n")
    qid = random.randint(0, 0xFFFF)
    header = struct.pack(HEADER_FMT, qid, 0x0100, 1, 0, 0, 0)
    print(f";; query wire header (12 bytes): {header.hex()}")
    print(f";;   id={qid} flags=rd qd=1 an=0 ns=0 ar=0\n")

    for server, msg in resolve(qname):
        wire = msg.to_wire()
        hid, flags, qd, an, ns, ar = parse_header(wire)
        label = SERVERS[server].zone.origin
        print(f";; {server}  (zone: {label})")
        print(f";;   ->>HEADER<<- opcode: QUERY, status: NOERROR, id {hid}")
        print(f";;   flags: {flags_str(flags)}; QUERY: {qd}, ANSWER: {an}, "
              f"AUTHORITY: {ns}, ADDITIONAL: {ar}")
        if msg.question:
            print(f";;   QUESTION SECTION:")
            print(f";;   {msg.question.qname:<28} IN  A")
        if msg.answers:
            print(f";;   ANSWER SECTION:")
            for rr in msg.answers:
                print(f";;   {rr.name:<28} {rr.ttl:<6} IN  A  {rr.rdata}")
        if msg.authority:
            print(f";;   AUTHORITY SECTION:")
            for rr in msg.authority:
                print(f";;   {rr.name:<28} {rr.ttl:<6} IN  NS {rr.rdata}")
        if msg.additional:
            print(f";;   ADDITIONAL SECTION:")
            for rr in msg.additional:
                print(f";;   {rr.name:<28} {rr.ttl:<6} IN  A  {rr.rdata}")
        print()


def lame_delegation_demo() -> None:
    """A lame delegation: NS points at a server that is NOT authoritative for the
    zone, so the response comes back without the AA bit set."""
    print(";; LAME DELEGATION: example.com NS -> ns1.other.net (not authoritative)")
    flags = 0x8000  # response, but NO aa bit
    msg = DNSMessage(
        id=0xBEEF, flags=flags, question=Question("example.com.", TYPE_A, CLASS_IN),
        authority=[ResourceRecord("example.com.", TYPE_NS, CLASS_IN, 3600, "ns1.other.net", 6)],
    )
    _, fl, _, an, ns, _ = parse_header(msg.to_wire())
    print(f";;   flags: {flags_str(fl)}; ANSWER: {an}, AUTHORITY: {ns}")
    print(";;   ^^^ aa absent -> server is NOT authoritative; delegation is lame.\n")


def main() -> None:
    random.seed(42)
    print("=" * 72)
    print(" DNS +trace simulation  (RFC 1035 message format, iterative walk)")
    print("=" * 72)
    print_trace("www.example.com.")
    print("=" * 72)
    print(" Failure-mode demo")
    print("=" * 72)
    lame_delegation_demo()
    print(";; dig +trace retraces from root once it sees the missing AA bit,")
    print(";; exactly the evidence you use when hunting a bad glue record.")


if __name__ == "__main__":
    main()
