#!/usr/bin/env python3
"""Offline IPFIX (RFC 7011) and NetFlow v9/v5 template parser.

This is the offline counterpart to ``nfcapd`` -- the real collector would
parse the same wire bytes from UDP/4739 (IPFIX), UDP/9995 (v9), or
UDP/2055 (v5). The script:

  * Decodes a single synthetic IPFIX packet containing one Template Set
    (FlowSet ID 2) and one Data Set.
  * Walks the binary record layout, mapping each Information Element ID
    to a name from a subset of the IANA registry (RFC 7012 / iana.org).
  * Distinguishes key fields (scope) from non-key fields for accounting.
  * Aggregates per-flow octets/packets by (src, dst, proto, port) tuple
    and prints the top talkers -- the same report the carrier bills on.

The synthetic input below mirrors what ``softflowd`` or a Linux
``nfacctd`` instance would emit. No third-party libraries.
"""

from __future__ import annotations

import ipaddress
import struct
from dataclasses import dataclass, field
from typing import ClassVar

VERSION_IPFIX = 10
VERSION_NFV9 = 9

FLOWSET_TEMPLATE = 2
FLOWSET_OPTIONS_TEMPLATE = 3

OCTET_COUNT_IE = 1
PACKET_COUNT_IE = 2
PROTOCOL_IE = 4
DSCP_IE = 5
SRC_PORT_IE = 7
SRC_IPV4_IE = 8
DST_IPV4_IE = 12
TCP_FLAGS_IE = 6
FLOW_START_IE = 152
FLOW_END_IE = 153

IE_NAMES: dict[int, tuple[str, int]] = {
    1: ("octetDeltaCount", 8),
    2: ("packetDeltaCount", 8),
    3: ("packetTotalCount", 8),
    4: ("protocolIdentifier", 1),
    5: ("classOfServiceIPv4", 1),
    6: ("tcpControlBits", 1),
    7: ("sourceTransportPort", 2),
    8: ("srcIPv4Address", 4),
    10: ("ingressInterface", 4),
    12: ("dstIPv4Address", 4),
    14: ("egressInterface", 4),
    16: ("bgpSourceAsNumber", 4),
    17: ("bgpDestinationAsNumber", 4),
    152: ("flowStartSysUpTime", 4),
    153: ("flowEndSysUpTime", 4),
}

PROTO_NAMES = {1: "icmp", 6: "tcp", 17: "udp", 47: "gre", 50: "esp", 58: "icmp6"}


@dataclass(frozen=True)
class IERecord:
    element_id: int
    length: int
    enterprise: bool
    name: str

    @property
    def byte_length(self) -> int:
        if self.enterprise:
            return self.length + 4
        return self.length


@dataclass(frozen=True)
class Template:
    template_id: int
    fields: tuple[IERecord, ...]
    scope_fields: tuple[IERecord, ...] = ()

    def record_length(self) -> int:
        return sum(ie.byte_length for ie in self.fields)


@dataclass
class FlowRecord:
    key: tuple
    octets: int
    packets: int
    tcp_flags: int
    start_ms: int
    end_ms: int
    dscp: int

    def duration_ms(self) -> int:
        return max(self.end_ms - self.start_ms, 0)


@dataclass
class IPFIXParser:
    templates: dict[int, Template] = field(default_factory=dict)
    records: list[dict[str, object]] = field(default_factory=list)
    flows: dict[tuple, FlowRecord] = field(default_factory=dict)

    HEADER_STRUCT: ClassVar[struct.Struct] = struct.Struct("!HHIII")

    def parse(self, packet: bytes) -> None:
        version, length, export_time, sequence, observation_domain = (
            self.HEADER_STRUCT.unpack_from(packet, 0)
        )
        if version == VERSION_IPFIX:
            print(
                f"[header] version={version} (IPFIX) length={length} "
                f"export_time={export_time} sequence={sequence} "
                f"observation_domain={observation_domain}"
            )
        elif version == VERSION_NFV9:
            print(
                f"[header] version={version} (NetFlow v9) length={length} "
                f"export_time={export_time} sequence={sequence} "
                f"observation_domain={observation_domain}"
            )
        else:
            raise ValueError(f"unsupported NetFlow version {version}")

        cursor = self.HEADER_STRUCT.size
        cursor = self._parse_flowsets(packet, cursor, length)

    def _parse_flowsets(self, packet: bytes, cursor: int, total_length: int) -> int:
        while cursor + 4 <= total_length:
            flowset_id, flowset_length = struct.unpack_from("!HH", packet, cursor)
            flowset_end = cursor + flowset_length
            if flowset_id == FLOWSET_TEMPLATE:
                self._parse_template(packet, cursor + 4, flowset_end, flowset_length)
            elif flowset_id == FLOWSET_OPTIONS_TEMPLATE:
                print(f"[flowset id={flowset_id} length={flowset_length}]  OPTIONS TEMPLATE (skipped)")
            elif flowset_id >= 256:
                self._parse_data(packet, cursor + 4, flowset_end, flowset_id, flowset_length)
            else:
                print(f"[flowset id={flowset_id} length={flowset_length}]  unknown")
            cursor = flowset_end
        return cursor

    def _parse_template(self, packet: bytes, cursor: int, end: int, flowset_length: int) -> None:
        while cursor + 4 <= end:
            template_id, field_count = struct.unpack_from("!HH", packet, cursor)
            cursor += 4
            fields: list[IERecord] = []
            for _ in range(field_count):
                if cursor + 4 > end:
                    raise ValueError("template truncated")
                element_id, element_length = struct.unpack_from("!HH", packet, cursor)
                cursor += 4
                enterprise = (element_id & 0x8000) != 0
                if enterprise:
                    element_id &= 0x7FFF
                    cursor += 1
                name, fixed_length = IE_NAMES.get(
                    element_id, (f"IE_{element_id}", element_length)
                )
                fields.append(
                    IERecord(
                        element_id=element_id,
                        length=fixed_length,
                        enterprise=enterprise,
                        name=name,
                    )
                )
            tpl = Template(template_id=template_id, fields=tuple(fields))
            self.templates[template_id] = tpl
            print(
                f"[flowset id=2 length={flowset_length}]  TEMPLATE "
                f"id={template_id} field_count={field_count}"
            )
            for idx, ie in enumerate(fields, start=1):
                ent = " [enterprise]" if ie.enterprise else ""
                print(f"    [{idx}]  IE {ie.element_id:<5} {ie.name:<22} {ie.length}B{ent}")

    def _parse_data(self, packet: bytes, cursor: int, end: int, template_id: int, flowset_length: int) -> None:
        tpl = self.templates.get(template_id)
        if tpl is None:
            print(f"[flowset id={template_id} length={flowset_length}]  DATA -- missing template")
            return
        record_length = tpl.record_length()
        print(
            f"[flowset id={template_id} length={flowset_length}]  DATA "
            f"(template_id={template_id}) record_length={record_length}"
        )
        record_index = 0
        while cursor + record_length <= end:
            record_index += 1
            offset = cursor
            decoded: dict[str, object] = {}
            for ie in tpl.fields:
                value_bytes = packet[offset : offset + ie.byte_length]
                offset += ie.byte_length
                if ie.element_id in (SRC_IPV4_IE, DST_IPV4_IE):
                    value = str(ipaddress.IPv4Address(value_bytes))
                elif ie.element_id == PROTOCOL_IE:
                    value = int.from_bytes(value_bytes, "big")
                elif ie.element_id == SRC_PORT_IE:
                    value = int.from_bytes(value_bytes, "big")
                elif ie.element_id == TCP_FLAGS_IE:
                    value = int.from_bytes(value_bytes, "big")
                elif ie.element_id == DSCP_IE:
                    value = int.from_bytes(value_bytes, "big")
                elif ie.element_id == OCTET_COUNT_IE:
                    value = int.from_bytes(value_bytes, "big")
                elif ie.element_id == PACKET_COUNT_IE:
                    value = int.from_bytes(value_bytes, "big")
                else:
                    value = int.from_bytes(value_bytes, "big")
                decoded[ie.name] = value
            self._aggregate(decoded)
            print(f"  record[{record_index}] " + " ".join(
                f"{k}={v}" for k, v in decoded.items()
            ))
            cursor += record_length

    def _aggregate(self, rec: dict[str, object]) -> None:
        src = rec.get("srcIPv4Address", "0.0.0.0")
        dst = rec.get("dstIPv4Address", "0.0.0.0")
        proto = rec.get("protocolIdentifier", 0)
        sport = rec.get("sourceTransportPort", 0)
        key = (str(src), str(dst), int(proto), int(sport))
        flow = self.flows.get(key)
        if flow is None:
            self.flows[key] = FlowRecord(
                key=key,
                octets=int(rec.get("octetDeltaCount", 0)),
                packets=int(rec.get("packetDeltaCount", 0)),
                tcp_flags=int(rec.get("tcpControlBits", 0)),
                start_ms=int(rec.get("flowStartSysUpTime", 0)),
                end_ms=int(rec.get("flowEndSysUpTime", 0)),
                dscp=int(rec.get("classOfServiceIPv4", 0)),
            )
            return
        flow.octets += int(rec.get("octetDeltaCount", 0))
        flow.packets += int(rec.get("packetDeltaCount", 0))
        flow.tcp_flags |= int(rec.get("tcpControlBits", 0))


def build_synthetic_packet() -> bytes:
    """Build one IPFIX packet with a template + data records."""
    template_ies: list[tuple[int, int, bool]] = [
        (SRC_IPV4_IE, 4, False),
        (DST_IPV4_IE, 4, False),
        (PROTOCOL_IE, 1, False),
        (SRC_PORT_IE, 2, False),
        (OCTET_COUNT_IE, 8, False),
        (PACKET_COUNT_IE, 8, False),
        (TCP_FLAGS_IE, 1, False),
        (DSCP_IE, 1, False),
        (FLOW_START_IE, 4, False),
        (FLOW_END_IE, 4, False),
    ]
    template_set = struct.pack("!HH", 256, len(template_ies))
    for eid, length, _ in template_ies:
        template_set += struct.pack("!HH", eid, length)

    flows = [
        ("10.10.1.2", "10.10.2.2", 6, 443, 1_716_840, 1240, 0x18, 46, 1000, 16000),
        ("10.10.2.2", "10.10.1.2", 6, 51234, 144_360, 1198, 0x18, 46, 1010, 16100),
        ("10.10.1.2", "10.10.2.2", 17, 53, 1_240, 12, 0x00, 26, 2000, 22000),
    ]
    data_records = b""
    for src, dst, proto, sport, octets, pkts, flags, dscp, s, e in flows:
        data_records += ipaddress.IPv4Address(src).packed
        data_records += ipaddress.IPv4Address(dst).packed
        data_records += struct.pack("!B", proto)
        data_records += struct.pack("!H", sport)
        data_records += struct.pack("!Q", octets)
        data_records += struct.pack("!Q", pkts)
        data_records += struct.pack("!B", flags)
        data_records += struct.pack("!B", dscp)
        data_records += struct.pack("!I", s)
        data_records += struct.pack("!I", e)
    data_set = struct.pack("!HH", 256, 4 + len(data_records)) + data_records

    template_header = struct.pack("!HH", FLOWSET_TEMPLATE, 4 + 4 + 4 * len(template_ies))
    flowsets = template_header + template_set + data_set
    export_time = 1748208000
    header = struct.pack("!HHIII", VERSION_IPFIX, 16 + len(flowsets), export_time, 1, 42)
    return header + flowsets


def main() -> None:
    print("=" * 64)
    print("IPFIX PARSER -- synthetic single-packet export")
    print("=" * 64)
    packet = build_synthetic_packet()
    parser = IPFIXParser()
    parser.parse(packet)

    print()
    print("=" * 64)
    print("ACCOUNTING -- per-flow totals (top talkers)")
    print("=" * 64)
    flows = sorted(parser.flows.values(), key=lambda f: f.octets, reverse=True)
    for f in flows:
        src, dst, proto, sport = f.key
        name = PROTO_NAMES.get(proto, str(proto))
        print(
            f"  {src:>15} -> {dst:<15} {name:<5} sp={sport:<6} "
            f"pkts={f.packets:<6} octets={f.octets:<10} "
            f"tcp_flags=0x{f.tcp_flags:02x} dscp={f.dscp:<3} "
            f"dur={f.duration_ms()}ms"
        )
    print()
    print(f"Total flows seen: {len(flows)}")


if __name__ == "__main__":
    main()