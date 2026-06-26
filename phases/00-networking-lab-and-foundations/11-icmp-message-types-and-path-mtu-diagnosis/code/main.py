"""
ICMP message types, ping/traceroute mechanics, and Path MTU Discovery (PMTUD).

A stdlib-only model that lets you inspect the byte-level structure of ICMP
messages, compute the Internet checksum (RFC 1071), simulate a traceroute by
decrementing TTL and emitting Time Exceeded (type 11) replies, and run the
Path MTU Discovery algorithm (RFC 1191, RFC 8201 / RFC 1989 for IPv6).

No network access, no third-party deps. Run: python3 main.py
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# ICMP type/code registry (RFC 792 + later assignments)
# ---------------------------------------------------------------------------
ICMP_TYPES: Dict[int, str] = {
    0: "Echo Reply",
    3: "Destination Unreachable",
    4: "Source Quench (deprecated)",
    5: "Redirect",
    8: "Echo Request",
    9: "Router Advertisement",
    10: "Router Solicitation",
    11: "Time Exceeded",
    12: "Parameter Problem",
    13: "Timestamp",
    14: "Timestamp Reply",
}

# Destination Unreachable codes (RFC 792) -- code 4 is the PMTUD workhorse.
DEST_UNREACHABLE_CODES: Dict[int, str] = {
    0: "Net Unreachable",
    1: "Host Unreachable",
    2: "Protocol Unreachable",
    3: "Port Unreachable",
    4: "Fragmentation Needed and DF Set (PMTUD)",
    5: "Source Route Failed",
}

TIME_EXCEEDED_CODES: Dict[int, str] = {
    0: "TTL Exceeded in Transit",
    1: "Fragment Reassembly Time Exceeded",
}


# ---------------------------------------------------------------------------
# Internet checksum -- RFC 1071 / RFC 792
# ---------------------------------------------------------------------------
def internet_checksum(data: bytes) -> int:
    """RFC 1071 one's-complement 16-bit sum over the message, checksum field = 0."""
    total = 0
    length = len(data)
    for i in range(0, length - 1, 2):
        total += (data[i] << 8) | data[i + 1]
    if length & 1:  # odd trailing byte, pad with zero
        total += data[length - 1] << 8
    while total >> 16:  # fold 32 bits into 16
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


# ---------------------------------------------------------------------------
# ICMP message builders
# ---------------------------------------------------------------------------
@dataclass
class IcmpMessage:
    type_: int
    code: int
    rest: bytes  # 4-byte "rest of header" (id+seq, or unused, or next-hop MTU)
    payload: bytes = b""

    def to_bytes(self) -> bytes:
        header = struct.pack("!BBH", self.type_, self.code, 0) + self.rest
        body = header + self.payload
        csum = internet_checksum(body)
        return struct.pack("!BBH", self.type_, self.code, csum) + self.rest + self.payload

    @staticmethod
    def parse(raw: bytes) -> "IcmpMessage":
        type_, code, csum = struct.unpack("!BBH", raw[:4])
        rest = raw[4:8]
        payload = raw[8:]
        if internet_checksum(raw) != 0:
            raise ValueError(f"bad ICMP checksum: got 0x{csum:04x}")
        return IcmpMessage(type_, code, rest, payload)


def echo_request(ident: int, seq: int, payload: bytes = b"ping-from-lab") -> IcmpMessage:
    rest = struct.pack("!HH", ident & 0xFFFF, seq & 0xFFFF)
    return IcmpMessage(8, 0, rest, payload)


def echo_reply(ident: int, seq: int, payload: bytes) -> IcmpMessage:
    rest = struct.pack("!HH", ident & 0xFFFF, seq & 0xFFFF)
    return IcmpMessage(0, 0, rest, payload)


def frag_needed(next_hop_mtu: int) -> IcmpMessage:
    """RFC 792 Destination Unreachable, code 4 'fragmentation needed and DF set'.

    The 4-byte 'rest of header' carries the next-hop MTU (low 16 bits usable on
    classic RFC 792; RFC 1191 defines the full MTU in those 16 bits)."""
    rest = struct.pack("!HH", 0, next_hop_mtu & 0xFFFF)
    return IcmpMessage(3, 4, rest)


def time_exceeded(code: int = 0) -> IcmpMessage:
    """Type 11. Code 0 = TTL expired (this is what traceroute collects)."""
    return IcmpMessage(11, code, b"\x00\x00\x00\x00")


# ---------------------------------------------------------------------------
# Path MTU Discovery -- RFC 1191 (IPv4) / RFC 8201 (IPv6, was RFC 1989)
# ---------------------------------------------------------------------------
RFC1191_PLATEAUS: List[int] = [68, 296, 508, 1006, 1280, 1492, 2002, 4352, 4470, 9216]


def next_plateau(current_mtu: int) -> int:
    """Largest plateau strictly less than current_mtu (RFC 1191)."""
    candidates = [p for p in RFC1191_PLATEAUS if p < current_mtu]
    return max(candidates) if candidates else 68


@dataclass
class PmtudState:
    mtu: int
    history: List[Tuple[int, str]] = field(default_factory=list)

    def reduce_to(self, new_mtu: int, reason: str) -> None:
        self.mtu = new_mtu
        self.history.append((new_mtu, reason))


def path_mtu_discover(initial_mtu: int, frag_needed_mtu: int) -> PmtudState:
    """Simulate one round of PMTUD: a DF-set probe of `initial_mtu` triggers an
    ICMP type 3 code 4 carrying `frag_needed_mtu`. Per RFC 1191, round the
    reported MTU UP to the nearest plateau; if the report is stale (< 68) step
    down one plateau instead."""
    state = PmtudState(initial_mtu)
    state.history.append((initial_mtu, "initial DF probe (RFC 1191)"))

    reported = frag_needed_mtu if frag_needed_mtu >= 68 else next_plateau(initial_mtu)
    rounded = min((p for p in RFC1191_PLATEAUS if p >= reported), default=reported)
    if rounded == reported and frag_needed_mtu < 68:
        rounded = next_plateau(initial_mtu)

    state.reduce_to(rounded, f"ICMP type 3 code 4, reported={frag_needed_mtu}, rounded={rounded}")
    return state


# ---------------------------------------------------------------------------
# Traceroute model: each hop with TTL k provokes a Time Exceeded from hop k
# ---------------------------------------------------------------------------
@dataclass
class Hop:
    ttl: int
    router: str
    icmp_type: int
    icmp_code: int
    rtt_ms: float


def traceroute(path: List[str], rtt_base: float = 5.0) -> List[Hop]:
    """Given ordered router hostnames, model traceroute: a probe with TTL=k is
    expired by the k-th router, which returns ICMP type 11 code 0. The final
    hop (destination) returns ICMP type 0 (Echo Reply) instead."""
    hops: List[Hop] = []
    for idx, router in enumerate(path, start=1):
        rtt = round(rtt_base * idx + (idx % 2), 2)
        if idx == len(path):
            hops.append(Hop(idx, router, 0, 0, rtt))
        else:
            hops.append(Hop(idx, router, 11, 0, rtt))
    return hops


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
def main() -> None:
    print("=== ICMP type/code registry (RFC 792 + later) ===")
    for t, name in ICMP_TYPES.items():
        print(f"  type {t:>2}: {name}")
    print(f"  DU code 4: {DEST_UNREACHABLE_CODES[4]}")
    print(f"  TE code 0: {TIME_EXCEEDED_CODES[0]}")

    print("\n=== Echo Request/Reply round-trip with RFC 1071 checksum ===")
    req = echo_request(ident=0x1234, seq=1, payload=b"networks-lab")
    raw = req.to_bytes()
    print(f"  Echo Request bytes ({len(raw)}): {raw.hex()}")
    rep = echo_reply(ident=0x1234, seq=1, payload=b"networks-lab")
    parsed = IcmpMessage.parse(rep.to_bytes())
    assert parsed.type_ == 0 and parsed.code == 0
    print(f"  Echo Reply parsed: type={parsed.type_} id+seq={parsed.rest.hex()}")

    print("\n=== traceroute model (TTL-k -> Time Exceeded at hop k) ===")
    path = ["10.0.0.1", "10.0.1.1", "10.0.2.1", "203.0.113.10"]
    for h in traceroute(path):
        kind = "Echo Reply (destination)" if h.icmp_type == 0 else "Time Exceeded"
        print(f"  ttl={h.ttl:<2} {h.router:<15} type={h.icmp_type} code={h.icmp_code} "
              f"({kind}) rtt={h.rtt_ms}ms")

    print("\n=== Path MTU Discovery (RFC 1191) ===")
    print(f"  RFC 1191 plateaus: {RFC1191_PLATEAUS}")
    s1 = path_mtu_discover(initial_mtu=1500, frag_needed_mtu=1492)
    print(f"  1500 over PPPoE (report 1492): {s1.history}")
    s2 = path_mtu_discover(initial_mtu=1492, frag_needed_mtu=0)
    print(f"  1492, stale report=0: {s2.history}")
    s3 = path_mtu_discover(initial_mtu=1500, frag_needed_mtu=1280)
    print(f"  1500 -> 1280 (IPv6 floor, RFC 8201): {s3.history}")

    print("\n=== ICMP Frag Needed message bytes ===")
    fn = frag_needed(next_hop_mtu=1492)
    fn_raw = fn.to_bytes()
    print(f"  type={fn.type_} code={fn.code} next-hop-mtu=1492")
    print(f"  bytes: {fn_raw.hex()}")
    parsed_fn = IcmpMessage.parse(fn_raw)
    mtu_back = struct.unpack("!H", parsed_fn.rest[2:4])[0]
    print(f"  parsed back: type={parsed_fn.type_} code={parsed_fn.code} mtu={mtu_back}")


if __name__ == "__main__":
    main()
