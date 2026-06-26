"""IEEE 802.1Q VLAN tag parser and per-VLAN bridge learning-table simulator.

This stdlib-only program supports the "Virtual LANs to Bridge Learning Table"
lab. It does two things:

1. parse_8021q_frame() decodes a raw hex Ethernet frame, verifies the 802.1Q
   Tag Protocol Identifier (TPID 0x8100), and unpacks the 16-bit Tag Control
   Information field into PCP (3 bits, 802.1p priority), DEI/CFI (1 bit), and
   the 12-bit VLAN Identifier (VID).

2. BridgeLearningTable models a VLAN-aware transparent bridge. Its forwarding
   database is keyed on the compound key (vid, src_mac) so the same MAC may
   legitimately appear on different ports in different VLANs. Rows age out with
   the IEEE 802.1D default of 300 seconds. The simulator replays a frame
   sequence and prints each learn / flood / forward decision.

No pip dependencies, no network access. Run: python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

TPID_8021Q = 0x8100          # fixed Tag Protocol Identifier for a C-VLAN tag
DEFAULT_AGING_SECONDS = 300  # IEEE 802.1D default forwarding-database aging
MAX_TAGGED_FRAME = 1522      # 802.3 1518 + 4-byte tag
BROADCAST_MAC = "ff:ff:ff:ff:ff:ff"

VlanKey = Tuple[int, str]


@dataclass
class ParsedFrame:
    """Result of decoding one Ethernet frame."""

    dst_mac: str
    src_mac: str
    tagged: bool
    vid: Optional[int]
    pcp: Optional[int]
    dei: Optional[int]
    ethertype: int
    total_len: int


def _hex_to_bytes(frame_hex: str) -> bytes:
    cleaned = "".join(frame_hex.split()).replace("0x", "")
    if len(cleaned) % 2 != 0:
        raise ValueError("hex frame has an odd number of nibbles")
    return bytes.fromhex(cleaned)


def _mac(raw: bytes) -> str:
    return ":".join(f"{b:02x}" for b in raw)


def parse_8021q_frame(frame_hex: str) -> ParsedFrame:
    """Decode a hex Ethernet frame, recognizing an optional 802.1Q tag.

    Layout (bytes): dst[6] src[6] [TPID[2] TCI[2]] ethertype[2] payload...
    """
    raw = _hex_to_bytes(frame_hex)
    if len(raw) < 14:
        raise ValueError("frame shorter than a 14-byte Ethernet header")

    dst = _mac(raw[0:6])
    src = _mac(raw[6:12])
    maybe_tpid = (raw[12] << 8) | raw[13]

    if maybe_tpid == TPID_8021Q:
        tci = (raw[14] << 8) | raw[15]
        pcp = (tci >> 13) & 0x07          # top 3 bits
        dei = (tci >> 12) & 0x01          # next 1 bit
        vid = tci & 0x0FFF                # low 12 bits
        ethertype = (raw[16] << 8) | raw[17]
        return ParsedFrame(dst, src, True, vid, pcp, dei, ethertype, len(raw))

    return ParsedFrame(dst, src, False, None, None, None, maybe_tpid, len(raw))


def describe_vid(vid: int) -> str:
    if vid == 0:
        return "priority-tagged only (no VLAN)"
    if vid == 4095:
        return "reserved"
    if vid == 1:
        return "default / native VLAN"
    return "user VLAN"


@dataclass
class FdbRow:
    port: int
    age: int = 0  # seconds since last seen


@dataclass
class BridgeLearningTable:
    """VLAN-aware forwarding database keyed on (vid, src_mac)."""

    aging_seconds: int = DEFAULT_AGING_SECONDS
    # vid -> list of ports that carry that VLAN (membership / labels)
    port_membership: Dict[int, List[int]] = field(default_factory=dict)
    _fdb: Dict[VlanKey, FdbRow] = field(default_factory=dict)

    def label_port(self, port: int, vid: int) -> None:
        self.port_membership.setdefault(vid, [])
        if port not in self.port_membership[vid]:
            self.port_membership[vid].append(port)

    def learn(self, vid: int, src_mac: str, port: int) -> None:
        self._fdb[(vid, src_mac)] = FdbRow(port=port, age=0)

    def lookup(self, vid: int, dst_mac: str) -> Optional[int]:
        row = self._fdb.get((vid, dst_mac))
        return row.port if row else None

    def age(self, elapsed: int) -> List[VlanKey]:
        """Advance all rows by `elapsed` seconds, evicting expired entries."""
        evicted: List[VlanKey] = []
        for key, row in list(self._fdb.items()):
            row.age += elapsed
            if row.age >= self.aging_seconds:
                evicted.append(key)
                del self._fdb[key]
        return evicted

    def egress_set(self, vid: int, ingress_port: int) -> List[int]:
        ports = self.port_membership.get(vid, [])
        return [p for p in ports if p != ingress_port]

    def forward(self, frame: ParsedFrame, ingress_port: int) -> Tuple[str, List[int]]:
        """Return (decision, egress_ports) for a tagged frame."""
        if not frame.tagged or frame.vid is None:
            return ("dropped: untagged on VLAN trunk", [])

        vid = frame.vid
        self.learn(vid, frame.src_mac, ingress_port)
        candidates = self.egress_set(vid, ingress_port)

        if not candidates:
            return ("black-holed: no egress port labeled with VID", [])

        if frame.dst_mac == BROADCAST_MAC:
            return ("flood (broadcast)", candidates)

        known_port = self.lookup(vid, frame.dst_mac)
        if known_port is None:
            return ("flood (unknown unicast in this VLAN)", candidates)
        if known_port == ingress_port:
            return ("filtered (dst on ingress port)", [])
        return ("forward (known unicast)", [known_port])

    def dump(self) -> str:
        if not self._fdb:
            return "  (empty)"
        lines = ["  VID  MAC                Port  Age(s)"]
        for (vid, mac), row in sorted(self._fdb.items()):
            lines.append(f"  {vid:<4} {mac}  {row.port:<4}  {row.age}")
        return "\n".join(lines)


def _demo_parser() -> None:
    print("=" * 64)
    print("802.1Q TAG PARSER")
    print("=" * 64)

    # Tagged frame: dst, src, TPID 8100, TCI a00a (PCP=5,DEI=0,VID=10), IPv4
    tagged = "ffffffffffff 001122aabb01 8100 a00a 0800 deadbeef"
    legacy = "001122aabb09 001122aabb01 0800 cafebabe"  # untagged IPv4

    for label, hexstr in (("tagged", tagged), ("legacy", legacy)):
        f = parse_8021q_frame(hexstr)
        print(f"\n[{label}] dst={f.dst_mac} src={f.src_mac}")
        if f.tagged:
            print(f"  TPID=0x8100  VID={f.vid} ({describe_vid(f.vid)})")
            print(f"  PCP={f.pcp} (802.1p priority)  DEI={f.dei}")
            print(f"  inner ethertype=0x{f.ethertype:04x}  bytes={f.total_len}")
        else:
            print(f"  untagged  ethertype=0x{f.ethertype:04x}  bytes={f.total_len}")
    print(f"\nMax tagged frame length: {MAX_TAGGED_FRAME} bytes "
          "(802.3 1518 + 4-byte tag); FCS must be recomputed.")


def _demo_bridge() -> None:
    print("\n" + "=" * 64)
    print("PER-VLAN BRIDGE LEARNING TABLE")
    print("=" * 64)

    bridge = BridgeLearningTable()
    # Port labels: p2/p4 carry VLAN 10 (gray); p3/p4 carry VLAN 20 (white).
    bridge.label_port(2, 10)
    bridge.label_port(4, 10)
    bridge.label_port(3, 20)
    bridge.label_port(4, 20)

    a_mac = "001122aabb01"  # VLAN 10 host on port 2
    b_mac = "001122aabb09"  # VLAN 10 host on port 4
    c_mac = "001122aabb0f"  # VLAN 20 host on port 3

    def tag(dst: str, src: str, vid: int, pcp: int = 0) -> ParsedFrame:
        tci = (pcp << 13) | (vid & 0x0FFF)
        hexstr = f"{dst} {src} 8100 {tci:04x} 0800 00"
        return parse_8021q_frame(hexstr)

    sequence = [
        ("A broadcasts ARP on VLAN 10", tag("ffffffffffff", a_mac, 10), 2),
        ("B replies to A on VLAN 10", tag(a_mac, b_mac, 10), 4),
        ("A unicasts to B (now learned)", tag(b_mac, a_mac, 10), 2),
        ("C broadcasts on VLAN 20", tag("ffffffffffff", c_mac, 20, pcp=5), 3),
        ("A tries to reach C across VLANs", tag(c_mac, a_mac, 10), 2),
    ]

    for desc, frame, ingress in sequence:
        decision, egress = bridge.forward(frame, ingress)
        print(f"\n> {desc}")
        print(f"  in:port{ingress} vid={frame.vid} dst={frame.dst_mac}")
        print(f"  decision: {decision}  egress={egress or '[]'}")

    print("\nForwarding database after sequence:")
    print(bridge.dump())

    print(f"\nAging by {DEFAULT_AGING_SECONDS}s (default 802.1D timer)...")
    evicted = bridge.age(DEFAULT_AGING_SECONDS)
    print(f"  evicted rows: {evicted}")
    print("Forwarding database after aging:")
    print(bridge.dump())


def main() -> None:
    _demo_parser()
    _demo_bridge()
    print("\nKey takeaway: a frame floods only on ports labeled with its VID.")
    print("A missing VID label on a trunk silently black-holes traffic.")


if __name__ == "__main__":
    main()
