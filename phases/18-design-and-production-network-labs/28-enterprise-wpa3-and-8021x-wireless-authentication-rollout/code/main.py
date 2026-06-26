#!/usr/bin/env python3
"""RADIUS Access-Accept decoder for per-user VLAN assignment.

When a FreeRADIUS server accepts an EAP-TLS authentication, it returns
a RADIUS Access-Accept packet (RFC 2865 §3) carrying attribute/value
pairs (AVPs). The AP / authenticator reads specific attributes to
authorize the supplicant's session -- the most common are the
Tunnel-attributes from RFC 2868:

  Tunnel-Type             = VLAN
  Tunnel-Medium-Type      = IEEE-802
  Tunnel-Private-Group-ID = <VLAN id or name>

This module parses a synthetic Access-Accept and prints the
authorization that the AP enforces. The same logic runs in production
fleet auditors: confirm the server emits what the AP reads, and the
AP reads what the policy says.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

CODE_ACCESS_ACCEPT = 2

ATTR_USER_NAME = 1
ATTR_TUNNEL_TYPE = 64
ATTR_TUNNEL_MEDIUM_TYPE = 65
ATTR_TUNNEL_PRIVATE_GROUP_ID = 81

TUNNEL_TYPE_NAMES = {1: "PPTP", 2: "L2F", 3: "L2TP", 4: "ATMP", 5: "VTP", 6: "AH", 7: "EAPOL", 8: "VLAN"}
TUNNEL_MEDIUM_NAMES = {1: "IPv4", 2: "IPv6", 3: "NSAP", 4: "HDLC", 5: "BBN-1822",
                       6: "802", 7: "E.163", 8: "E.164", 9: "F.69", 10: "X.121",
                       11: "IPX", 12: "AppleTalk", 13: "DecNet4", 14: "Banyan",
                       15: "E.164-NSAP"}


@dataclass(frozen=True)
class AVP:
    type: int
    value: bytes

    def decode_string(self) -> str:
        return self.value.decode("utf-8", errors="replace").rstrip("\x00")

    def decode_integer(self) -> int:
        return int.from_bytes(self.value, "big")


@dataclass(frozen=True)
class RadiusPacket:
    code: int
    identifier: int
    authenticator: bytes
    attributes: tuple[AVP, ...]

    def find(self, attr_type: int) -> AVP | None:
        for avp in self.attributes:
            if avp.type == attr_type:
                return avp
        return None

    def find_all(self, attr_type: int) -> list[AVP]:
        return [avp for avp in self.attributes if avp.type == attr_type]


def parse_radius_packet(packet: bytes) -> RadiusPacket:
    if len(packet) < 20:
        raise ValueError(f"RADIUS packet too short: {len(packet)} bytes")
    code, identifier, length, authenticator = struct.unpack_from("!BBH16s", packet, 0)
    if length != len(packet):
        raise ValueError(f"length mismatch: header says {length}, got {len(packet)}")
    attrs: list[AVP] = []
    cursor = 20
    while cursor < length:
        if cursor + 2 > length:
            raise ValueError("attribute header truncated")
        attr_type, attr_length = struct.unpack_from("!BB", packet, cursor)
        cursor += 2
        if cursor + attr_length - 2 > length:
            raise ValueError(f"attribute {attr_type} truncated")
        value = packet[cursor : cursor + attr_length - 2]
        cursor += attr_length - 2
        attrs.append(AVP(type=attr_type, value=value))
    return RadiusPacket(
        code=code, identifier=identifier,
        authenticator=authenticator, attributes=tuple(attrs),
    )


def build_synthetic_access_accept(user: str, vlan_id: int) -> bytes:
    auth = b"\xaa" * 16
    user_b = user.encode("utf-8")
    avps = [
        struct.pack("!BB", ATTR_USER_NAME, 2 + len(user_b)) + user_b,
        struct.pack("!BB", ATTR_TUNNEL_TYPE, 3 + 4) + struct.pack("!I", 8),
        struct.pack("!BB", ATTR_TUNNEL_MEDIUM_TYPE, 3 + 4) + struct.pack("!I", 6),
        struct.pack("!BB", ATTR_TUNNEL_PRIVATE_GROUP_ID, 2 + len(str(vlan_id))) + str(vlan_id).encode("utf-8"),
    ]
    payload = b"".join(avps)
    length = 20 + len(payload)
    header = struct.pack("!BBH", CODE_ACCESS_ACCEPT, 1, length) + auth
    return header + payload


def describe_authorization(pkt: RadiusPacket) -> str:
    user = pkt.find(ATTR_USER_NAME)
    tunnel_type = pkt.find(ATTR_TUNNEL_TYPE)
    tunnel_medium = pkt.find(ATTR_TUNNEL_MEDIUM_TYPE)
    tunnel_pvt = pkt.find(ATTR_TUNNEL_PRIVATE_GROUP_ID)
    out: list[str] = []
    out.append(f"  user={user.decode_string() if user else '<unknown>'}")
    if tunnel_type:
        type_name = TUNNEL_TYPE_NAMES.get(tunnel_type.decode_integer(),
                                           f"tunnel-type={tunnel_type.decode_integer()}")
        out.append(f"  Tunnel-Type={type_name}")
    if tunnel_medium:
        med_name = TUNNEL_MEDIUM_NAMES.get(tunnel_medium.decode_integer(),
                                            f"medium={tunnel_medium.decode_integer()}")
        out.append(f"  Tunnel-Medium-Type={med_name}")
    if tunnel_pvt:
        vlan = tunnel_pvt.decode_string()
        out.append(f"  Tunnel-Private-Group-ID={vlan}  -> assigned VLAN {vlan}")
    return "\n".join(out)


def main() -> None:
    print("=" * 64)
    print("RADIUS ACCESS-ACCEPT DECODER (RFC 2865 + RFC 2868)")
    print("=" * 64)
    samples = [
        ("cfo@acme.local", 100),
        ("contractor@acme.local", 200),
        ("noc-engineer@acme.local", 10),
    ]
    for user, vlan in samples:
        pkt_bytes = build_synthetic_access_accept(user, vlan)
        pkt = parse_radius_packet(pkt_bytes)
        print()
        print(f"[packet] code={pkt.code} identifier={pkt.identifier} "
              f"length={len(pkt_bytes)} auth=0x{pkt.authenticator.hex()[:16]}...")
        print(describe_authorization(pkt))
    print()
    print("=" * 64)
    print("HOW THIS DRIVES VLAN ASSIGNMENT")
    print("=" * 64)
    print("  FreeRADIUS reads the LDAP group, picks the VLAN number,")
    print("  and emits Tunnel-attributes in the Access-Accept reply.")
    print("  hostapd reads the Tunnel-attributes and assigns the")
    print("  supplicant to the matching VLAN ID. Each user lands on")
    print("  a network segment consistent with their directory group.")


if __name__ == "__main__":
    main()