#!/usr/bin/env python3
"""ICMP message encoder/decoder and MPLS label-stack simulator.

Covers Tanenbaum sections 5.6.4 (Internet Control Protocols) and 5.6.5
(Label Switching and MPLS). Stdlib only.

Part 1 - ICMP: encodes and decodes the most important ICMP message
types described in Fig. 5-60 (echo request/reply, destination
unreachable, time exceeded, parameter problem, redirect).  Each
message is carried encapsulated in an IP packet.

Part 2 - MPLS: simulates a label stack as described in Fig. 5-62 with
push / swap / pop operations across a three-LSR path, exactly mirroring
the label-swapping technique of Sec. 5.6.5.

Run:  python3 main.py
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

ICMP_TYPES: dict[int, str] = {
    0: "Echo Reply",
    3: "Destination Unreachable",
    4: "Source Quench",
    5: "Redirect",
    8: "Echo Request",
    11: "Time Exceeded",
    12: "Parameter Problem",
    13: "Timestamp Request",
    14: "Timestamp Reply",
}

DEST_UNREACHABLE_CODES: dict[int, str] = {
    0: "Net unreachable",
    1: "Host unreachable",
    2: "Protocol unreachable",
    3: "Port unreachable",
    4: "Fragmentation needed and DF set",
    5: "Source route failed",
}


@dataclass
class ICMPMessage:
    msg_type: int
    code: int
    checksum: int
    identifier: int
    sequence: int
    payload: bytes = b""

    @property
    def type_name(self) -> str:
        return ICMP_TYPES.get(self.msg_type, f"Unknown({self.msg_type})")

    @property
    def code_name(self) -> str:
        if self.msg_type == 3:
            return DEST_UNREACHABLE_CODES.get(self.code, f"code {self.code}")
        return f"code {self.code}"


def icmp_checksum(data: bytes) -> int:
    if len(data) % 2 == 1:
        data = data + b"\x00"
    total = 0
    for i in range(0, len(data), 2):
        word = (data[i] << 8) | data[i + 1]
        total += word
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def encode_icmp(msg: ICMPMessage) -> bytes:
    header = struct.pack("!BBHHH", msg.msg_type, msg.code, 0,
                         msg.identifier, msg.sequence)
    body = msg.payload
    cksum = icmp_checksum(header + body)
    return struct.pack("!BBHHH", msg.msg_type, msg.code, cksum,
                       msg.identifier, msg.sequence) + body


def decode_icmp(raw: bytes) -> ICMPMessage:
    if len(raw) < 8:
        raise ValueError("ICMP message too short")
    msg_type, code, cksum, ident, seq = struct.unpack("!BBHHH", raw[:8])
    payload = raw[8:]
    return ICMPMessage(
        msg_type=msg_type,
        code=code,
        checksum=cksum,
        identifier=ident,
        sequence=seq,
        payload=payload,
    )


def validate_icmp(raw: bytes) -> bool:
    return icmp_checksum(raw) == 0


@dataclass
class IPPacket:
    """Minimal IP pseudo-header wrapper used to carry ICMP."""
    src: str
    dst: str
    ttl: int
    protocol: int
    payload: bytes

    def to_bytes(self) -> bytes:
        ver_ihl = (4 << 4) | 5
        tos = 0
        total_len = 20 + len(self.payload)
        ident = 0
        flags_frag = 0
        src_int = _ip_to_int(self.src)
        dst_int = _ip_to_int(self.dst)
        hdr = struct.pack(
            "!BBHHHBBHII",
            ver_ihl, tos, total_len, ident, flags_frag,
            self.ttl, self.protocol, 0, src_int, dst_int,
        )
        return hdr + self.payload


def _ip_to_int(ip: str) -> int:
    val = 0
    for part in ip.split("."):
        val = (val << 8) | int(part)
    return val


@dataclass
class MPLSLabel:
    label: int
    qos: int
    s_bit: int
    ttl: int

    def to_bytes(self) -> bytes:
        a = (self.label >> 4) & 0xFF
        b = ((self.label & 0x0F) << 4) | ((self.qos & 0x07) << 1) | (self.s_bit & 0x01)
        c = self.ttl & 0xFF
        return struct.pack("!BBB", a, b, c)


def encode_mpls_stack(labels: list[MPLSLabel]) -> bytes:
    out = b""
    for i, lbl in enumerate(labels):
        lbl.s_bit = 1 if i == len(labels) - 1 else 0
        out += lbl.to_bytes()
    return out


def parse_mpls_stack(raw: bytes) -> list[MPLSLabel]:
    labels: list[MPLSLabel] = []
    offset = 0
    while offset + 4 <= len(raw):
        a, b, c = struct.unpack("!BBB", raw[offset:offset + 3])
        label = (a << 4) | (b >> 4)
        qos = (b >> 1) & 0x07
        s_bit = b & 0x01
        ttl = c
        labels.append(MPLSLabel(label, qos, s_bit, ttl))
        offset += 4
        if s_bit:
            break
    return labels


@dataclass
class LSR:
    """Label Switched Router with an incoming->outgoing label table."""
    name: str
    label_table: dict[int, tuple[int, str]] = field(default_factory=dict)
    pop_on: Optional[int] = None

    def process(self, pkt_label: int) -> tuple[str, int, bool]:
        if pkt_label not in self.label_table:
            raise KeyError(f"{self.name}: label {pkt_label} not in table")
        new_label, next_hop = self.label_table[pkt_label]
        pop = False
        if self.pop_on is not None and self.pop_on == pkt_label:
            pop = True
        return next_hop, new_label, pop


def simulate_mpls_path() -> None:
    lsr1 = LSR("LER-Ingress", {0: (100, "LSR-Core")})
    lsr2 = LSR("LSR-Core", {100: (200, "LSR-Egress")})
    lsr3 = LSR("LSR-Egress", {200: (0, "Destination")})
    lsr3.pop_on = 200
    path = [lsr1, lsr2, lsr3]
    label = 0
    current = "Host-A"
    print(f"  Start: current={current}  label={label}")
    for hop in path:
        next_hop, new_label, pop = hop.process(label)
        action = "POP" if pop else "SWAP"
        print(f"  {hop.name:<12}: in={label:<5} -> {action} out={new_label:<5} "
              f"next_hop={next_hop}")
        label = new_label
        current = next_hop
    print(f"  Delivered to {current} (label popped, plain IP)")


def main() -> None:
    print("=" * 64)
    print("ICMP Encoder/Decoder  --  Tanenbaum 5.6.4")
    print("=" * 64)

    echo_req = ICMPMessage(
        msg_type=8, code=0, checksum=0,
        identifier=0x1234, sequence=1,
        payload=b"PING-DATA",
    )
    raw = encode_icmp(echo_req)
    decoded = decode_icmp(raw)
    print("Echo Request:")
    print(f"  type={decoded.type_name}  code={decoded.code_name}")
    print(f"  id=0x{decoded.identifier:04X}  seq={decoded.sequence}")
    print(f"  payload={decoded.payload!r}")
    print(f"  checksum=0x{decoded.checksum:04X}  valid={validate_icmp(raw)}")
    print(f"  raw: {raw.hex(' ')}")

    print()
    dest_unreach = ICMPMessage(
        msg_type=3, code=4, checksum=0,
        identifier=0, sequence=0,
        payload=struct.pack("!HH", 1500, 0),
    )
    raw2 = encode_icmp(dest_unreach)
    dec2 = decode_icmp(raw2)
    print("Destination Unreachable (fragmentation needed, DF set):")
    print(f"  type={dec2.type_name}  code={dec2.code_name}")
    print(f"  payload={dec2.payload.hex(' ')}")
    print(f"  checksum valid={validate_icmp(raw2)}")

    print()
    time_exceeded = ICMPMessage(
        msg_type=11, code=0, checksum=0,
        identifier=0, sequence=0, payload=b"\x00" * 8,
    )
    raw3 = encode_icmp(time_exceeded)
    dec3 = decode_icmp(raw3)
    print("Time Exceeded:")
    print(f"  type={dec3.type_name}  code={dec3.code_name}")
    print(f"  checksum valid={validate_icmp(raw3)}")

    print()
    print("=" * 64)
    print("ICMP carried in an IP packet")
    print("=" * 64)
    pkt = IPPacket(
        src="10.0.0.1", dst="10.0.0.2", ttl=64,
        protocol=1, payload=raw,
    )
    pkt_bytes = pkt.to_bytes()
    print(f"  IP header + ICMP ({len(pkt_bytes)} bytes): {pkt_bytes.hex(' ')}")

    print()
    print("=" * 64)
    print("MPLS Label Stack Simulator  --  Tanenbaum 5.6.5")
    print("=" * 64)
    print("MPLS header (4 bytes): Label(20) QoS(3) S(1) TTL(8)")
    print()
    stack = [
        MPLSLabel(label=100, qos=2, s_bit=0, ttl=255),
        MPLSLabel(label=200, qos=1, s_bit=1, ttl=254),
    ]
    encoded = encode_mpls_stack(stack)
    print(f"  Encoded stack: {encoded.hex(' ')}")
    parsed = parse_mpls_stack(encoded)
    for lbl in parsed:
        print(f"  label={lbl.label} qos={lbl.qos} S={lbl.s_bit} TTL={lbl.ttl}")

    print()
    print("Label-swapping path: Host-A -> LER-Ingress -> LSR-Core "
          "-> LSR-Egress -> Destination")
    print("-" * 64)
    simulate_mpls_path()


if __name__ == "__main__":
    main()