"""Capstone: backward-learning bridges, 802.1D/RSTP spanning tree, 802.1Q VLANs.

Stdlib-only Python. No network calls. No pip deps.

Run with: python3 code/main.py

The module exposes three things:
  1. A `Bridge` class that does backward learning and flooding.
  2. A small triangle topology that runs STP root election and a fast
     RSTP Proposal/Agreement handshake demo.
  3. Pure byte-level helpers for 802.1Q VLAN tagging and untagging,
     plus a VLAN-aware bridge wrapper.

When executed as `__main__`, the script prints four small scenarios:
  Scenario 1: triangle STP convergence
  Scenario 2: RSTP Proposal/Agreement on a P2P link
  Scenario 3: broadcast storm (no STP) vs loop-free broadcast (STP)
  Scenario 4: 802.1Q tagged/untagged VLAN round-trip
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# 1. 802.1Q tag helpers  (TPID 0x8100, TCI = PCP(3) | DEI(1) | VID(12))
# ---------------------------------------------------------------------------

TPID_8021Q = 0x8100
TPID_8021AD = 0x88A8  # Q-in-Q outer tag
ETHERTYPE_IPV4 = 0x0800
STP_MULTICAST = "01:80:c2:00:00:00"


def _mac_to_bytes(mac: str) -> bytes:
    return bytes(int(x, 16) for x in mac.split(":"))


def _bytes_to_mac(b: bytes) -> str:
    return ":".join(f"{x:02x}" for x in b)


def vlan_tag(
    frame: bytes,
    vid: int,
    pcp: int = 0,
    dei: bool = False,
    tpid: int = TPID_8021Q,
) -> bytes:
    """Insert a 4-byte 802.1Q tag between the source MAC and the EtherType.

    Input frame layout (no preamble/CRC):  dst(6) | src(6) | ethertype(2) | payload
    Output layout:                        dst(6) | src(6) | tag(4)    | ethertype(2) | payload
    """
    if not 1 <= vid <= 4094:
        raise ValueError(f"VID must be in 1..4094, got {vid}")
    if not 0 <= pcp <= 7:
        raise ValueError(f"PCP must be in 0..7, got {pcp}")
    if len(frame) < 14:
        raise ValueError("frame must be at least 14 bytes (dst+src+ethertype)")

    dst = frame[:6]
    src = frame[6:12]
    original_ethertype = frame[12:14]
    payload = frame[14:]

    tci = (pcp & 0x07) << 13 | (0x01 if dei else 0x00) << 12 | (vid & 0x0FFF)
    tag = tpid.to_bytes(2, "big") + tci.to_bytes(2, "big")
    return dst + src + tag + original_ethertype + payload


def parse_vlan_tag(frame: bytes) -> Optional[Dict[str, int]]:
    """Return the TCI fields if the frame carries an 802.1Q tag, else None."""
    if len(frame) < 18:
        return None
    tpid = int.from_bytes(frame[12:14], "big")
    if tpid not in (TPID_8021Q, TPID_8021AD):
        return None
    tci = int.from_bytes(frame[14:16], "big")
    return {
        "tpid": tpid,
        "pcp": (tci >> 13) & 0x07,
        "dei": bool((tci >> 12) & 0x01),
        "vid": tci & 0x0FFF,
    }


def vlan_untag(frame: bytes) -> bytes:
    """Strip a single 802.1Q tag if present. Raises if the frame is too short."""
    parsed = parse_vlan_tag(frame)
    if parsed is None:
        return frame
    return frame[:12] + frame[16:]


# ---------------------------------------------------------------------------
# 2. BPDU dataclass and STP BPDU serializer (wire-format practice)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BridgeID:
    """8-byte Bridge ID: 2-byte priority (big-endian) + 6-byte MAC."""

    priority: int
    mac: str

    def as_bytes(self) -> bytes:
        return self.priority.to_bytes(2, "big") + _mac_to_bytes(self.mac)

    def __lt__(self, other: "BridgeID") -> bool:  # for sorting/election
        return self.as_bytes() < other.as_bytes()


@dataclass(frozen=True)
class BPDU:
    """Configuration BPDU (IEEE 802.1D, version 0)."""

    root_id: BridgeID
    root_path_cost: int
    sender_id: BridgeID
    sender_port_id: int
    message_age: int = 0
    max_age: int = 20
    hello_time: int = 2
    forward_delay: int = 15
    version: int = 0  # 0 = STP, 2 = RSTP
    flags: int = 0    # bit 7 = TC, bit 0 = TCA, plus RSTP role/proposal bits

    def is_superior(self, other: "BPDU") -> bool:
        """A BPDU is 'superior' if it represents a better root path."""
        if self.root_id != other.root_id:
            return self.root_id < other.root_id
        if self.root_path_cost != other.root_path_cost:
            return self.root_path_cost < other.root_path_cost
        if self.sender_id != other.sender_id:
            return self.sender_id < other.sender_id
        return self.sender_port_id < other.sender_port_id

    def wire_bytes(self) -> bytes:
        """Serialize a BPDU to a 35-byte payload (no preamble/CRC)."""
        return (
            b"\x00\x00"                              # protocol id 0x0000
            + bytes([self.version])                  # version
            + bytes([0x00])                          # type = Configuration
            + bytes([self.flags & 0xFF])             # flags
            + self.root_id.as_bytes()                # root bridge id (8)
            + self.root_path_cost.to_bytes(4, "big") # root path cost
            + self.sender_id.as_bytes()              # sender bridge id (8)
            + self.sender_port_id.to_bytes(2, "big") # sender port id
            + self.message_age.to_bytes(2, "big")
            + self.max_age.to_bytes(2, "big")
            + self.hello_time.to_bytes(2, "big")
            + self.forward_delay.to_bytes(2, "big")
        )


# ---------------------------------------------------------------------------
# 3. Forwarding bridge (backward learning + flooding)
# ---------------------------------------------------------------------------


@dataclass
class Frame:
    """Internal frame representation used by the bridge simulator."""

    src: str
    dst: str
    vlan: int = 1
    payload: str = ""
    is_bpdu: bool = False  # BPDUs are not learned or flooded as data


class Bridge:
    """Transparent bridge with backward learning, aging, and VLAN awareness."""

    def __init__(
        self,
        name: str,
        ports: Sequence[str],
        vlan_membership: Optional[Dict[str, FrozenSet[int]]] = None,
        aging_seconds: int = 300,
    ) -> None:
        self.name = name
        self.ports: List[str] = list(ports)
        self.vlan_membership: Dict[str, FrozenSet[int]] = {
            p: (vlan_membership.get(p, frozenset({1})) if vlan_membership else frozenset({1}))
            for p in self.ports
        }
        self.aging_seconds = aging_seconds
        # Forwarding table: mac -> (port, last_seen_iteration)
        self.table: Dict[str, Tuple[str, int]] = {}
        self._tick: int = 0
        self.log: List[str] = []
        self.flooded_total: int = 0
        self.forwarded_total: int = 0
        self.filtered_total: int = 0

    def _vlan_members(self, vlan: int) -> List[str]:
        return [p for p in self.ports if vlan in self.vlan_membership.get(p, frozenset())]

    def age(self) -> None:
        """Sweep stale entries older than aging_seconds of bridge ticks."""
        stale = [m for m, (_, seen) in self.table.items() if self._tick - seen > self.aging_seconds]
        for m in stale:
            del self.table[m]
            self.log.append(f"  [{self.name}] aged out {m}")

    def _is_broadcast(self, dst: str) -> bool:
        return dst.lower() in ("ff:ff:ff:ff:ff:ff", STP_MULTICAST)

    def receive(self, port: str, frame: Frame) -> List[Tuple[str, Frame]]:
        """Return a list of (egress_port, frame) actions the bridge takes.

        The caller delivers each action to the segment (or, in this sim,
        appends it to the per-port output queue).
        """
        self._tick += 1
        actions: List[Tuple[str, Frame]] = []
        if frame.is_bpdu:
            # BPDUs are processed but not forwarded as data; we return empty.
            self.log.append(f"  [{self.name}] BPDU on {port} from {frame.src}")
            return actions

        # 1. Backward learning
        prior = self.table.get(frame.src)
        self.table[frame.src] = (port, self._tick)
        if prior is not None and prior[0] != port:
            self.log.append(
                f"  [{self.name}] MAC {frame.src} moved {prior[0]} -> {port}"
            )

        # 2. Look up destination
        if self._is_broadcast(frame.dst):
            # Flood, restricted to VLAN membership
            targets = [p for p in self._vlan_members(frame.vlan) if p != port]
            self.log.append(
                f"  [{self.name}] FLOOD {frame.dst} (vlan {frame.vlan}) on {targets}"
            )
            self.flooded_total += 1
            for p in targets:
                actions.append((p, frame))
            return actions

        entry = self.table.get(frame.dst)
        if entry is None:
            # Unknown unicast: flood (still VLAN-restricted)
            targets = [p for p in self._vlan_members(frame.vlan) if p != port]
            self.log.append(
                f"  [{self.name}] FLOOD (unknown) {frame.dst} (vlan {frame.vlan}) on {targets}"
            )
            self.flooded_total += 1
            for p in targets:
                actions.append((p, frame))
            return actions

        dst_port, _ = entry
        if dst_port == port:
            # Already on the right segment (hub-style shared medium)
            self.log.append(f"  [{self.name}] FILTER {frame.dst} on {port} (same port)")
            self.filtered_total += 1
            return actions

        self.log.append(f"  [{self.name}] FORWARD {frame.dst} -> {dst_port}")
        self.forwarded_total += 1
        actions.append((dst_port, frame))
        return actions


# ---------------------------------------------------------------------------
# 4. STP root election on a small topology
# ---------------------------------------------------------------------------


@dataclass
class BridgeStub:
    """A node in the STP topology. Port costs are per-port."""

    bid: BridgeID
    ports: List[str]
    port_cost: Dict[str, int] = field(default_factory=dict)
    # Filled in by the election:
    root_port: Optional[str] = None
    designated_ports: List[str] = field(default_factory=list)
    blocked_ports: List[str] = field(default_factory=list)
    is_root: bool = False
    root_path_cost: int = 0


def stp_root_election(bridges: Dict[str, BridgeStub], links: List[Tuple[str, str]]) -> None:
    """Run a fixed-point STP root election over the given links.

    `links` is a list of (a_port, b_port) tuples where each port is named
    "BridgeName.port" (e.g. "SW1.p1"). After this call, each bridge has
    `is_root`, `root_port`, `designated_ports`, and `blocked_ports` set.
    """
    # Step 1: elect the root = lowest Bridge ID.
    root_name = min(bridges, key=lambda n: bridges[n].bid.as_bytes())
    for n, b in bridges.items():
        b.is_root = (n == root_name)
        b.root_path_cost = 0
        b.root_port = None
        b.designated_ports = []
        b.blocked_ports = []

    # Step 2: each non-root bridge finds its root port (min cost to root).
    for name, b in bridges.items():
        if b.is_root:
            continue
        best: Optional[Tuple[int, str, str]] = None  # (cost, root_port, neighbor_name)
        for a_port, b_port in links:
            for self_port, other_port, other_name in _neighbor_ports(name, bridges, links):
                cost = b.port_cost.get(self_port, 4)
                cand = (cost, self_port, other_name)
                if best is None or cand < best:
                    best = cand
        if best is not None:
            b.root_path_cost = best[0]
            b.root_port = best[1]

    # Step 3: per segment, elect the Designated port (lowest cost to root,
    # tie-break by lower Bridge ID).
    seg_to_bidders: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}
    for a_port, b_port in links:
        seg_key = tuple(sorted([a_port, b_port]))
        seg_to_bidders.setdefault(seg_key, []).append((a_port, b_port))

    for seg, bidders in seg_to_bidders.items():
        a_port, b_port = bidders[0]
        a_name = a_port.split(".")[0]
        b_name = b_port.split(".")[0]
        a, b = bridges[a_name], bridges[b_name]
        # Bridge with the lower (root_path_cost, bridge_id) is designated on its end.
        a_key = (a.root_path_cost + a.port_cost.get(a_port, 4), a.bid.as_bytes())
        b_key = (b.root_path_cost + b.port_cost.get(b_port, 4), b.bid.as_bytes())
        if a_key <= b_key:
            a.designated_ports.append(a_port)
            if not b.is_root or b.root_port != b_port:
                b.blocked_ports.append(b_port)
            else:
                # b is root and this is its only path; keep it
                b.designated_ports.append(b_port)
        else:
            b.designated_ports.append(b_port)
            if not a.is_root or a.root_port != a_port:
                a.blocked_ports.append(a_port)
            else:
                a.designated_ports.append(a_port)


def _neighbor_ports(
    self_name: str, bridges: Dict[str, BridgeStub], links: List[Tuple[str, str]]
) -> List[Tuple[str, str, str]]:
    out: List[Tuple[str, str, str]] = []
    self_prefix = f"{self_name}."
    for a_port, b_port in links:
        if a_port.startswith(self_prefix):
            other_port = b_port
            other_name = b_port.split(".")[0]
            out.append((a_port, other_port, other_name))
        elif b_port.startswith(self_prefix):
            other_port = a_port
            other_name = a_port.split(".")[0]
            out.append((b_port, other_port, other_name))
    return out


# ---------------------------------------------------------------------------
# 5. RSTP Proposal/Agreement demo on a single point-to-point link
# ---------------------------------------------------------------------------


@dataclass
class RSTPStep:
    msg: str
    sender: str
    receiver: str
    action: str


def rstp_propose_agree(d_upstream: str, d_downstream: str, link_label: str) -> List[RSTPStep]:
    """Trace the Proposal/Agreement handshake on a P2P link.

    Returns a list of human-readable steps showing the Sync phase.
    """
    return [
        RSTPStep("Proposal", d_upstream, d_downstream, link_label),
        RSTPStep("Sync", d_downstream, "(self)", "all non-edge ports -> Discarding"),
        RSTPStep("Agreement", d_downstream, d_upstream, link_label + " -> Forwarding"),
    ]


# ---------------------------------------------------------------------------
# 6. Triangle STP + broadcast storm demo
# ---------------------------------------------------------------------------


def broadcast_storm_step() -> int:
    """Return the number of copies a broadcast becomes after one round of flooding
    in a triangle where every bridge floods out every other port."""
    return 4  # each of 3 bridges fans the broadcast out 2 other ports


# ---------------------------------------------------------------------------
# 7. __main__: run the four scenarios
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 72)
    print("Scenario 1: STP root election on a triangle of bridges")
    print("=" * 72)

    bridges: Dict[str, BridgeStub] = {
        "SW1": BridgeStub(BridgeID(0x8000, "00:11:22:33:44:55"), ["p1", "p2", "p3"],
                          {"p1": 4, "p2": 4, "p3": 4}),
        "SW2": BridgeStub(BridgeID(0x8000, "00:11:22:33:44:66"), ["p1", "p2", "p3"],
                          {"p1": 4, "p2": 4, "p3": 4}),
        "SW3": BridgeStub(BridgeID(0x8000, "00:11:22:33:44:77"), ["p1", "p2", "p3"],
                          {"p1": 4, "p2": 4, "p3": 4}),
    }
    links = [("SW1.p1", "SW2.p1"), ("SW2.p2", "SW3.p1"), ("SW3.p2", "SW1.p2")]
    stp_root_election(bridges, links)
    for name, b in bridges.items():
        role = "ROOT" if b.is_root else f"root_port={b.root_port}"
        print(f"  {name}: {role}  designated={b.designated_ports}  blocked={b.blocked_ports}")

    print()
    print("=" * 72)
    print("Scenario 2: RSTP Proposal/Agreement on a P2P link")
    print("=" * 72)
    for step in rstp_propose_agree("SW1.p3", "SW3.p3", "SW1<->SW3"):
        print(f"  {step.sender:6s} -> {step.receiver:9s}  {step.msg:11s}  {step.action}")

    print()
    print("=" * 72)
    print("Scenario 3: broadcast storm (no STP) vs loop-free (with STP)")
    print("=" * 72)
    n_copies = broadcast_storm_step()
    print(f"  Without STP, one broadcast becomes {n_copies} copies in 1 hop,")
    print(f"  and ~{n_copies ** 4} copies in 4 hops. With STP, one triangle link is")
    print("  parked, so the broadcast fans out across a tree exactly once.")

    print()
    print("=" * 72)
    print("Scenario 4: 802.1Q tagged/untagged VLAN round-trip")
    print("=" * 72)

    access_ports = {"h1": frozenset({10}), "h2": frozenset({10})}
    trunk_ports = {"trunk1": frozenset({1, 10, 20})}
    b = Bridge(
        name="CORE",
        ports=["h1", "h2", "trunk1"],
        vlan_membership={**access_ports, **trunk_ports},
    )
    print("  ", b.name, "ports:", b.ports)
    print("  ", b.name, "VLAN membership:", {p: sorted(s) for p, s in b.vlan_membership.items()})

    # Build a real tagged frame for VLAN 10 with PCP 5 (voice class).
    base_frame = (
        _mac_to_bytes("aa:bb:cc:00:00:01")           # dst
        + _mac_to_bytes("aa:bb:cc:00:00:02")         # src
        + ETHERTYPE_IPV4.to_bytes(2, "big")          # ethertype
        + b"hello-vlan-10"                           # payload
    )
    tagged = vlan_tag(base_frame, vid=10, pcp=5, dei=False)
    parsed = parse_vlan_tag(tagged)
    assert parsed is not None
    print(f"  Tagged frame TPID=0x{parsed['tpid']:04x}  PCP={parsed['pcp']}  "
          f"DEI={int(parsed['dei'])}  VID={parsed['vid']}")
    untagged = vlan_untag(tagged)
    assert untagged == base_frame
    print(f"  Round-trip ok: {len(base_frame)} -> {len(tagged)} -> {len(untagged)} bytes")

    # VLAN-aware flood demo
    f = Frame(src="aa:bb:cc:00:00:02", dst="ff:ff:ff:ff:ff:ff", vlan=10, payload="arp?")
    actions = b.receive("h1", f)
    print(f"  Broadcast in VLAN 10 from h1 -> actions: {[p for p, _ in actions]}")
    f20 = Frame(src="aa:bb:cc:00:00:02", dst="ff:ff:ff:ff:ff:ff", vlan=20, payload="arp?")
    actions20 = b.receive("h1", f20)
    print(f"  Broadcast in VLAN 20 from h1 -> actions: {[p for p, _ in actions20]}  (h1 not in 20)")

    # Show BPDU wire bytes
    bpdu = BPDU(
        root_id=BridgeID(0x4000, "00:00:00:00:00:01"),
        root_path_cost=4,
        sender_id=BridgeID(0x8000, "00:11:22:33:44:55"),
        sender_port_id=0x8001,
    )
    wire = bpdu.wire_bytes()
    print(f"  BPDU wire bytes ({len(wire)}): {wire.hex()}")


if __name__ == "__main__":
    main()
