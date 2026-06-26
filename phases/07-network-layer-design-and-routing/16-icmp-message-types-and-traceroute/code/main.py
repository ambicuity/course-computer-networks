#!/usr/bin/env python3
"""ICMP Message Types and Traceroute (RFC 792, RFC 1191).

Demonstrates the core mechanisms described in the lesson:

  1. checksum        - RFC 1071 one's complement checksum over arbitrary data.
  2. ICMPMessage     - Build and parse every major ICMP message type as raw
                       bytes, verifying the Type/Code/Checksum fields.
  3. simulate_ping   - ICMP Echo request/reply cycle with RTT measurement.
  4. simulate_traceroute - TTL-based hop discovery (Van Jacobson, 1987):
                           sends probes with TTL=1,2,3,... and collects the
                           ICMP Time Exceeded (Type 11 Code 0) messages that
                           each router returns when it decrements TTL to zero.

Stdlib only.  Run: python3 code/main.py
"""

from __future__ import annotations

import struct
import time
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# RFC 1071 checksum
# ---------------------------------------------------------------------------

def checksum(data: bytes) -> int:
    """Compute the RFC 1071 one's complement checksum of *data*.

    Pad to an even length if necessary, sum all 16-bit words, fold the
    carry bits, and return the one's complement of the sum.
    The result fits in a 16-bit unsigned integer.
    """
    if len(data) % 2:
        data += b'\x00'
    s = 0
    for i in range(0, len(data), 2):
        word = (data[i] << 8) + data[i + 1]
        s += word
    # Fold 32-bit sum into 16 bits
    s = (s >> 16) + (s & 0xFFFF)
    s += s >> 16
    return ~s & 0xFFFF


def verify_checksum(data: bytes) -> bool:
    """Return True if the RFC 1071 checksum of *data* is 0x0000.

    When the checksum field in an ICMP header is correct, re-computing
    checksum over the entire message (including the checksum field) yields 0.
    """
    return checksum(data) == 0


# ---------------------------------------------------------------------------
# ICMP message type / code catalog (RFC 792)
# ---------------------------------------------------------------------------

ICMP_TYPES = {
    0:  ("Echo Reply",              {0: "echo reply"}),
    3:  ("Destination Unreachable", {
            0: "net unreachable",
            1: "host unreachable",
            2: "protocol unreachable",
            3: "port unreachable",
            4: "fragmentation needed, DF set",
            13: "communication administratively prohibited",
        }),
    4:  ("Source Quench",           {0: "source quench (deprecated)"}),
    5:  ("Redirect",                {
            0: "redirect for network",
            1: "redirect for host",
            2: "redirect for TOS and network",
            3: "redirect for TOS and host",
        }),
    8:  ("Echo Request",            {0: "echo request"}),
    11: ("Time Exceeded",           {
            0: "TTL exceeded in transit",
            1: "fragment reassembly time exceeded",
        }),
    12: ("Parameter Problem",       {0: "pointer indicates the error"}),
    13: ("Timestamp Request",       {0: "timestamp request"}),
    14: ("Timestamp Reply",         {0: "timestamp reply"}),
}


def describe_icmp(type_: int, code: int) -> str:
    """Return a human-readable label for an ICMP type/code pair."""
    if type_ not in ICMP_TYPES:
        return f"Unknown Type {type_}"
    name, codes = ICMP_TYPES[type_]
    code_desc = codes.get(code, f"code {code}")
    return f"Type {type_} ({name}) / Code {code}: {code_desc}"


# ---------------------------------------------------------------------------
# ICMP message builder / parser
# ---------------------------------------------------------------------------

@dataclass
class ICMPMessage:
    """An ICMP message with its wire-format bytes.

    Fields mirror the RFC 792 common header:
      type (1 B) | code (1 B) | checksum (2 B) | type-specific data ...
    """
    type_: int
    code: int
    identifier: int = 0       # Echo / Timestamp: 16-bit identifier
    sequence: int = 0         # Echo: sequence number
    payload: bytes = b''      # Echo: arbitrary data; error msgs: IP hdr + 8 B
    raw: bytes = field(default_factory=bytes, repr=False)

    # --- constructors -------------------------------------------------------

    @classmethod
    def echo_request(cls, identifier: int, sequence: int,
                     data: bytes = b'') -> "ICMPMessage":
        """Build an ICMP Echo Request (Type 8, Code 0)."""
        return cls._build_echo(8, identifier, sequence, data)

    @classmethod
    def echo_reply(cls, identifier: int, sequence: int,
                   data: bytes = b'') -> "ICMPMessage":
        """Build an ICMP Echo Reply (Type 0, Code 0)."""
        return cls._build_echo(0, identifier, sequence, data)

    @classmethod
    def time_exceeded(cls, original_ip_header: bytes,
                      original_first8: bytes) -> "ICMPMessage":
        """Build ICMP Time Exceeded, TTL in Transit (Type 11, Code 0).

        The body is: 4 unused bytes + original IP header + first 8 bytes of
        original datagram payload (RFC 792).
        """
        body = b'\x00' * 4 + original_ip_header + original_first8
        return cls._build_simple(11, 0, body)

    @classmethod
    def destination_unreachable(cls, code: int, original_ip_header: bytes,
                                original_first8: bytes,
                                next_hop_mtu: int = 0) -> "ICMPMessage":
        """Build ICMP Destination Unreachable (Type 3).

        For code 4 (frag needed) RFC 1191 places next-hop MTU in the
        upper 16 bits of the 'unused' 4-byte field.
        """
        if code == 4:
            unused = struct.pack('!HH', 0, next_hop_mtu)
        else:
            unused = b'\x00' * 4
        body = unused + original_ip_header + original_first8
        return cls._build_simple(3, code, body)

    # --- internal builders --------------------------------------------------

    @classmethod
    def _build_echo(cls, type_: int, identifier: int, sequence: int,
                    data: bytes) -> "ICMPMessage":
        header = struct.pack('!BBHHH', type_, 0, 0, identifier, sequence)
        csum = checksum(header + data)
        header = struct.pack('!BBHHH', type_, 0, csum, identifier, sequence)
        raw = header + data
        return cls(type_=type_, code=0, identifier=identifier,
                   sequence=sequence, payload=data, raw=raw)

    @classmethod
    def _build_simple(cls, type_: int, code: int, body: bytes) -> "ICMPMessage":
        header = struct.pack('!BBH', type_, code, 0)
        csum = checksum(header + body)
        header = struct.pack('!BBH', type_, code, csum)
        raw = header + body
        return cls(type_=type_, code=code, payload=body, raw=raw)

    # --- parser -------------------------------------------------------------

    @classmethod
    def parse(cls, raw: bytes, skip_ip_header: bool = False) -> "ICMPMessage":
        """Parse an ICMP message from *raw* bytes.

        Set *skip_ip_header=True* when *raw* includes the 20-byte IPv4
        header prepended (as returned by raw sockets).  By default raw
        is treated as pure ICMP bytes.
        """
        if skip_ip_header and len(raw) >= 20:
            raw = raw[20:]
        if len(raw) < 8:
            raise ValueError(f"ICMP message too short: {len(raw)} bytes")
        type_, code, csum_wire = struct.unpack('!BBH', raw[:4])
        obj = cls(type_=type_, code=code, payload=raw[4:], raw=raw)
        if type_ in (0, 8, 13, 14):   # echo / timestamp carry id+seq
            if len(raw) >= 8:
                obj.identifier, obj.sequence = struct.unpack('!HH', raw[4:8])
                obj.payload = raw[8:]
        return obj

    # --- display ------------------------------------------------------------

    def __str__(self) -> str:
        csum_stored = struct.unpack('!H', self.raw[2:4])[0] if len(self.raw) >= 4 else 0
        valid = verify_checksum(self.raw)
        label = describe_icmp(self.type_, self.code)
        base = (
            f"  {label}\n"
            f"    wire bytes  : {len(self.raw):3d}\n"
            f"    checksum    : {csum_stored:#06x}  ({'valid' if valid else 'INVALID'})"
        )
        if self.type_ in (0, 8):
            base += (f"\n    identifier  : {self.identifier:#06x}"
                     f"\n    sequence    : {self.sequence}"
                     f"\n    payload len : {len(self.payload)} bytes")
        elif self.type_ in (11, 3):
            body = self.payload
            base += (f"\n    body        : 4 B unused + orig IP hdr + 8 B of "
                     f"orig payload ({len(body)} bytes total)")
            if self.type_ == 3 and self.code == 4 and len(body) >= 4:
                mtu = struct.unpack('!H', body[2:4])[0]
                base += f"\n    next-hop MTU: {mtu} bytes (RFC 1191)"
        return base


# ---------------------------------------------------------------------------
# Fake IP header builder (for error-message demos)
# ---------------------------------------------------------------------------

def fake_ip_header(src: str, dst: str, ttl: int = 64,
                   protocol: int = 17) -> bytes:
    """Build a minimal 20-byte IPv4 header (no options).

    Fields: version/IHL, DSCP/ECN, total length (20), ID, flags/frag offset,
    TTL, protocol, header checksum, src addr, dst addr.
    """
    src_bytes = bytes(int(x) for x in src.split('.'))
    dst_bytes = bytes(int(x) for x in dst.split('.'))
    hdr = struct.pack(
        '!BBHHHBBH4s4s',
        0x45,        # version=4, IHL=5
        0,           # DSCP/ECN
        20,          # total length (header only in this stub)
        random.randint(0, 65535),   # identification
        0,           # flags / fragment offset
        ttl,
        protocol,
        0,           # header checksum placeholder
        src_bytes,
        dst_bytes,
    )
    csum = checksum(hdr)
    hdr = hdr[:10] + struct.pack('!H', csum) + hdr[12:]
    return hdr


def fake_transport_first8(src_port: int, dst_port: int) -> bytes:
    """Return first 8 bytes of a UDP or TCP segment (src/dst ports + 4 B)."""
    return struct.pack('!HHI', src_port, dst_port, 0)


# ---------------------------------------------------------------------------
# Demo 1 — ICMP Echo request / reply (ping)
# ---------------------------------------------------------------------------

@dataclass
class PingResult:
    """One ping round-trip result."""
    seq: int
    rtt_ms: float
    replied: bool

    def __str__(self) -> str:
        if self.replied:
            return f"  seq={self.seq}  rtt={self.rtt_ms:.3f} ms"
        return f"  seq={self.seq}  timeout (no reply)"


def simulate_ping(
    src_ip: str = "10.0.0.1",
    dst_ip: str = "10.0.0.2",
    count: int = 4,
    rtt_base_ms: float = 12.0,
    loss_rate: float = 0.0,
) -> List[PingResult]:
    """Simulate ICMP Echo request/reply exchanges (ping).

    Builds real ICMP Echo Request bytes, parses them back, builds the
    corresponding Echo Reply, and verifies checksums at each step.
    """
    results: List[PingResult] = []
    identifier = 0xBEEF

    for seq in range(1, count + 1):
        # Build Echo Request
        payload = struct.pack('!d', time.monotonic()) + b'hello'
        req = ICMPMessage.echo_request(identifier, seq, payload)
        assert verify_checksum(req.raw), "Echo Request checksum invalid"

        # Simulate network delivery (random loss)
        lost = random.random() < loss_rate
        if lost:
            results.append(PingResult(seq=seq, rtt_ms=0.0, replied=False))
            continue

        # Simulate RTT with small jitter
        rtt = rtt_base_ms + random.uniform(-1.0, 1.0)

        # Build Echo Reply (Type 0) carrying same payload back
        rep = ICMPMessage.echo_reply(identifier, seq, payload)
        assert verify_checksum(rep.raw), "Echo Reply checksum invalid"

        # Parse it back to confirm round-trip integrity
        parsed = ICMPMessage.parse(rep.raw)
        assert parsed.type_ == 0
        assert parsed.identifier == identifier
        assert parsed.sequence == seq

        results.append(PingResult(seq=seq, rtt_ms=rtt, replied=True))

    return results


# ---------------------------------------------------------------------------
# Demo 2 — ICMP Time Exceeded (traceroute mechanism)
# ---------------------------------------------------------------------------

@dataclass
class HopRecord:
    """Traceroute result for one TTL value."""
    ttl: int
    router_ip: str
    rtt_ms: float
    icmp_type: int
    icmp_code: int
    timed_out: bool = False

    def __str__(self) -> str:
        if self.timed_out:
            return f"  {self.ttl:3d}  * * *  (no response — ICMP filtered)"
        label = describe_icmp(self.icmp_type, self.icmp_code)
        return (f"  {self.ttl:3d}  {self.router_ip:<16}  "
                f"{self.rtt_ms:6.2f} ms  [{label}]")


def simulate_traceroute(
    src_ip: str,
    dst_ip: str,
    path: List[Tuple[str, float]],       # [(router_ip, base_rtt_ms), ...]
    silent_hops: Optional[List[int]] = None,
    max_hops: int = 30,
) -> List[HopRecord]:
    """Simulate Van Jacobson's traceroute algorithm (1987).

    For each TTL from 1 to len(path)+1:
      - Send an ICMP Echo Request with that TTL.
      - The router at hop TTL decrements TTL to 0, drops the packet, and
        sends back an ICMP Time Exceeded (Type 11 Code 0).
      - Record the router's IP (from the ICMP source) and RTT.
      - When the destination replies with Echo Reply (Type 0), stop.

    *path* is a list of (router_ip, base_rtt_ms) for each hop; the last
    entry is the destination itself (it replies with Echo Reply).
    *silent_hops* is a list of 1-based TTL positions that do not respond
    (modeling routers that filter ICMP Time Exceeded).
    """
    silent = set(silent_hops or [])
    records: List[HopRecord] = []
    identifier = 0xCAFE

    for ttl, (hop_ip, base_rtt) in enumerate(path, start=1):
        if ttl > max_hops:
            break

        if ttl in silent:
            records.append(HopRecord(
                ttl=ttl, router_ip='*', rtt_ms=0.0,
                icmp_type=-1, icmp_code=-1, timed_out=True,
            ))
            continue

        # Build the outgoing probe (Echo Request with this TTL)
        probe = ICMPMessage.echo_request(identifier, ttl, b'probe')

        # Determine what ICMP response this hop generates
        is_destination = (ttl == len(path))
        rtt = base_rtt + random.uniform(-0.5, 0.5)

        if is_destination:
            # Destination sends Echo Reply (Type 0 Code 0)
            ip_hdr = fake_ip_header(hop_ip, src_ip, ttl=64)
            reply = ICMPMessage.echo_reply(identifier, ttl, b'probe')
            assert verify_checksum(reply.raw)
            icmp_type, icmp_code = 0, 0
        else:
            # Intermediate router: TTL → 0, router sends Time Exceeded
            orig_ip_hdr = fake_ip_header(src_ip, dst_ip, ttl=0)
            orig_first8 = probe.raw[:8]   # first 8 bytes of ICMP probe
            te = ICMPMessage.time_exceeded(orig_ip_hdr, orig_first8)
            assert verify_checksum(te.raw)
            icmp_type, icmp_code = 11, 0

        records.append(HopRecord(
            ttl=ttl,
            router_ip=hop_ip,
            rtt_ms=rtt,
            icmp_type=icmp_type,
            icmp_code=icmp_code,
        ))

        if is_destination:
            break

    return records


# ---------------------------------------------------------------------------
# Demo 3 — ICMP error message gallery
# ---------------------------------------------------------------------------

def build_error_gallery() -> List[Tuple[str, ICMPMessage]]:
    """Build one representative ICMP error message for each major type."""
    src = "192.168.1.10"
    dst = "8.8.8.8"
    orig_hdr = fake_ip_header(src, dst, ttl=1, protocol=17)  # UDP
    orig_8   = fake_transport_first8(54321, 33434)           # src_port, dst_port

    gallery = [
        ("TTL expired in transit (traceroute)",
         ICMPMessage.time_exceeded(orig_hdr, orig_8)),

        ("No route to destination network",
         ICMPMessage.destination_unreachable(0, orig_hdr, orig_8)),

        ("No route to destination host",
         ICMPMessage.destination_unreachable(1, orig_hdr, orig_8)),

        ("Transport protocol not supported",
         ICMPMessage.destination_unreachable(2, orig_hdr, orig_8)),

        ("No process on that UDP port",
         ICMPMessage.destination_unreachable(3, orig_hdr, orig_8)),

        ("PMTU black hole (DF=1, too large) — next-hop MTU=1450",
         ICMPMessage.destination_unreachable(4, orig_hdr, orig_8, next_hop_mtu=1450)),

        ("Firewall / admin prohibited",
         ICMPMessage.destination_unreachable(13, orig_hdr, orig_8)),
    ]
    return gallery


# ---------------------------------------------------------------------------
# Main demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    sep = "=" * 68
    random.seed(42)

    # ------------------------------------------------------------------
    # Demo 1 — ICMP echo request / reply (ping)
    # ------------------------------------------------------------------
    print(sep)
    print("DEMO 1 — ICMP Echo Request / Reply (ping) — 4 probes")
    print(sep)
    ping_results = simulate_ping(
        src_ip="192.168.0.10",
        dst_ip="93.184.216.34",   # example.com
        count=4,
        rtt_base_ms=28.4,
    )
    sent = len(ping_results)
    recv = sum(1 for r in ping_results if r.replied)
    rtts = [r.rtt_ms for r in ping_results if r.replied]
    for r in ping_results:
        print(r)
    if rtts:
        print(f"  --- ping statistics ---")
        print(f"  {sent} sent, {recv} received, "
              f"{(sent - recv) / sent * 100:.0f}% packet loss")
        print(f"  rtt min/avg/max = "
              f"{min(rtts):.3f}/{sum(rtts)/len(rtts):.3f}/{max(rtts):.3f} ms\n")

    # Verify the raw bytes
    probe = ICMPMessage.echo_request(0xBEEF, 1, b'verify')
    parsed = ICMPMessage.parse(probe.raw)
    print(f"  Echo Request raw bytes   : {probe.raw.hex()}")
    print(f"  Checksum valid?          : {verify_checksum(probe.raw)}")
    print(f"  Parsed type / id / seq  : {parsed.type_} / "
          f"{parsed.identifier:#06x} / {parsed.sequence}")
    print()

    # ------------------------------------------------------------------
    # Demo 2 — Traceroute simulation (Van Jacobson, 1987)
    # ------------------------------------------------------------------
    print(sep)
    print("DEMO 2 — Traceroute to 8.8.8.8 (simulated path, 6 hops)")
    print(sep)
    print("  Algorithm: send Echo Request with TTL=n, router at hop n")
    print("  decrements TTL to 0 → drops packet → sends Time Exceeded")
    print("  (Type 11 Code 0).  Destination sends Echo Reply (Type 0).")
    print()

    # path = [(router_ip, base_rtt_ms), ...]  last entry = destination
    simulated_path = [
        ("192.168.1.1",   2.0),    # hop 1: home router
        ("10.0.0.1",     10.5),    # hop 2: ISP edge
        ("172.16.5.2",   18.3),    # hop 3: ISP core
        ("203.0.113.9",  22.1),    # hop 4: silent (filtered)
        ("216.239.49.3", 26.8),    # hop 5: Google backbone
        ("8.8.8.8",      29.1),    # hop 6: destination
    ]
    hops = simulate_traceroute(
        src_ip="192.168.0.10",
        dst_ip="8.8.8.8",
        path=simulated_path,
        silent_hops=[4],           # hop 4 does not send Time Exceeded
    )
    for hop in hops:
        print(hop)
    print()
    print("  Note: * * * at hop 4 is ambiguous — the packet did reach hop 4")
    print("  (we see hop 5), but that router does not send ICMP Time Exceeded.")
    print("  This is common firewall policy, not necessarily a routing black hole.\n")

    # ------------------------------------------------------------------
    # Demo 3 — ICMP message type gallery
    # ------------------------------------------------------------------
    print(sep)
    print("DEMO 3 — ICMP Error Message Gallery (RFC 792 / RFC 1191)")
    print(sep)
    print("  Every error message carries: orig IP header + first 8 bytes of")
    print("  orig payload.  The 8 bytes capture the TCP/UDP src+dst ports,")
    print("  allowing the sender to identify the affected connection.\n")
    gallery = build_error_gallery()
    for scenario, msg in gallery:
        print(f"  Scenario: {scenario}")
        print(msg)
        print()

    # ------------------------------------------------------------------
    # Demo 4 — Checksum verification
    # ------------------------------------------------------------------
    print(sep)
    print("DEMO 4 — RFC 1071 Checksum Computation")
    print(sep)
    print("  RFC 1071: sum all 16-bit words, fold carry, take one's complement.")
    print("  Property: if you include the checksum field in the sum, result = 0.\n")

    # Show step-by-step: start with zero checksum, compute, patch, verify
    raw_no_csum = b'\x08\x00\x00\x00\xbe\xef\x00\x01' + b'hello probe'
    csum_val = checksum(raw_no_csum)
    raw_with_csum = raw_no_csum[:2] + struct.pack('!H', csum_val) + raw_no_csum[4:]
    valid = verify_checksum(raw_with_csum)
    print(f"  Step 1 — raw bytes (csum field = 0x0000):")
    print(f"           {raw_no_csum.hex(' ')}")
    print(f"  Step 2 — checksum({len(raw_no_csum)} bytes) = {csum_val:#06x}")
    print(f"  Step 3 — patch csum field:")
    print(f"           {raw_with_csum.hex(' ')}")
    print(f"  Step 4 — verify (recompute over full msg): result = 0x0000? {valid}\n")

    # Show a corrupted packet fails
    corrupted = bytearray(raw_with_csum)
    corrupted[8] ^= 0xFF    # flip bits in payload
    print(f"  Corrupted msg verify: {verify_checksum(bytes(corrupted))} "
          f"(bit-flip detected)\n")

    # ------------------------------------------------------------------
    # Demo 5 — ICMP type/code reference table
    # ------------------------------------------------------------------
    print(sep)
    print("DEMO 5 — ICMP Type / Code Reference Table (RFC 792)")
    print(sep)
    for type_num in sorted(ICMP_TYPES):
        name, codes = ICMP_TYPES[type_num]
        for code_num, code_desc in sorted(codes.items()):
            print(f"  Type {type_num:2d} Code {code_num:2d} : {name} — {code_desc}")
    print()

    print("All demonstrations complete.")


if __name__ == "__main__":
    main()
