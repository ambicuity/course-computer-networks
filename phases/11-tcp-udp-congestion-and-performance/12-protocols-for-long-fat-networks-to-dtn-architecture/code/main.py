#!/usr/bin/env python3
"""Long Fat Network (LFN) problems and DTN architecture simulator.

Stdlib only. Demonstrates Sec 6.6.6 and 6.7.1:

1. LFN problems: sequence number wraparound (232 at gigabit speeds),
   PAWS (Protection Against Wrapped Sequence numbers) using timestamps,
   window scaling (16-bit window field extended with a shift factor).
2. Bandwidth-delay product analysis for gigabit transcontinental links.
3. DTN architecture: store-carry-forward, intermittent contacts, bundle
   custody transfer, and routing with scheduled vs opportunistic contacts.

Run:  python3 main.py
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Part 1: Sequence number wraparound and PAWS
# ---------------------------------------------------------------------------

@dataclass
class PAWS:
    """Protection Against Wrapped Sequence numbers using timestamps."""
    last_timestamp: dict[str, int] = field(default_factory=dict)

    def check(self, conn_id: str, seq: int, timestamp: int) -> bool:
        """Return True if segment is new (not a stale duplicate)."""
        last_ts = self.last_timestamp.get(conn_id, 0)
        if timestamp < last_ts:
            return False
        self.last_timestamp[conn_id] = timestamp
        return True


def sequence_wrap_time(speed_gbps: float, mss: int = 1460) -> float:
    """Time to wrap 32-bit sequence space at given speed."""
    bytes_per_sec = speed_gbps * 1e9 / 8
    return (2**32) / bytes_per_sec


# ---------------------------------------------------------------------------
# Part 2: Window scaling
# ---------------------------------------------------------------------------

@dataclass
class WindowScale:
    """RFC 1323 window scale option: shift the 16-bit window field."""
    shift: int = 0

    def advertise(self, raw_window: int) -> int:
        return raw_window

    def actual_window(self, raw_window: int) -> int:
        return raw_window * (2 ** self.shift)

    def max_window(self) -> int:
        return 65535 * (2 ** self.shift)


# ---------------------------------------------------------------------------
# Part 3: DTN Architecture (store-carry-forward)
# ---------------------------------------------------------------------------

@dataclass
class Bundle:
    id: str
    source: str
    destination: str
    payload: bytes
    lifetime: int = 3600
    custodian: str = ""
    creation_time: float = 0.0

    def __str__(self) -> str:
        return f"Bundle({self.id}: {self.source}->{self.destination}, {len(self.payload)}B, custodian={self.custodian})"


@dataclass
class DTNNode:
    name: str
    storage: list[Bundle] = field(default_factory=list)
    contacts: dict[str, float] = field(default_factory=dict)

    def receive_bundle(self, bundle: Bundle) -> None:
        self.storage.append(bundle)
        print(f"    [{self.name}] stored {bundle}")

    def transfer_custody(self, bundle: Bundle, new_custodian: str) -> Bundle:
        bundle.custodian = new_custodian
        return bundle

    def forward_on_contact(self, peer: "DTNNode", bandwidth_kbps: float,
                           duration_s: float) -> list[Bundle]:
        """Forward bundles during a contact window."""
        transferred: list[Bundle] = []
        bytes_available = int(bandwidth_kbps * 1000 * duration_s / 8)
        remaining = self.storage[:]
        for b in remaining:
            if len(b.payload) <= bytes_available:
                peer.receive_bundle(self.transfer_custody(b, peer.name))
                self.storage.remove(b)
                bytes_available -= len(b.payload)
                transferred.append(b)
        return transferred


@dataclass
class DTNNetwork:
    nodes: dict[str, DTNNode] = field(default_factory=dict)

    def add_node(self, name: str) -> DTNNode:
        node = DTNNode(name=name)
        self.nodes[name] = node
        return node

    def simulate_contact(self, node_a: str, node_b: str,
                         bw_kbps: float, duration_s: float) -> None:
        a = self.nodes[node_a]
        b = self.nodes[node_b]
        print(f"  Contact: {node_a} -> {node_b} ({bw_kbps}kbps, {duration_s}s)")
        transferred = a.forward_on_contact(b, bw_kbps, duration_s)
        print(f"  Transferred {len(transferred)} bundles")


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("LFN Problem 1: Sequence Number Wraparound (Sec 6.6.6)")
    print("=" * 70)
    speeds = [(0.056, "56 kbps"), (10, "10 Mbps"), (100, "100 Mbps"),
              (1000, "1 Gbps"), (10000, "10 Gbps")]
    print(f"  {'Speed':>12}  {'Wrap time':>15}  {'MSL=120s safe?':>15}")
    for speed, label in speeds:
        wt = sequence_wrap_time(speed)
        safe = "YES" if wt > 120 else "NO (wraps before MSL!)"
        if wt > 3600:
            wt_str = f"{wt/3600:.1f} hours"
        elif wt > 60:
            wt_str = f"{wt/60:.1f} minutes"
        else:
            wt_str = f"{wt:.1f} seconds"
        print(f"  {label:>12}  {wt_str:>15}  {safe:>15}")
    print()
    print("  At 1 Gbps, 2^32 wraps in 34s -- well under the 120s MSL.")
    print("  Old packets could still exist when seq numbers recycle!")

    print()
    print("=" * 70)
    print("PAWS: Protection Against Wrapped Sequence numbers (RFC 1323)")
    print("=" * 70)
    paws = PAWS()
    segments = [
        (1000, 100, "normal segment"),
        (2000, 200, "normal segment"),
        (1000, 50, "stale duplicate (old timestamp)"),
        (3000, 300, "normal segment"),
    ]
    print(f"  {'Seq':>6}  {'TS':>6}  {'Verdict':>20}  {'Note':>25}")
    for seq, ts, note in segments:
        ok = paws.check("conn1", seq, ts)
        verdict = "ACCEPT" if ok else "REJECT (stale)"
        print(f"  {seq:6d}  {ts:6d}  {verdict:>20}  {note:>25}")
    print()
    print("  PAWS uses TCP timestamp option as logical extension of seq numbers.")
    print("  Segments with older timestamps are discarded even if seq looks valid.")

    print()
    print("=" * 70)
    print("LFN Problem 2: Window Scaling (RFC 1323)")
    print("=" * 70)
    configs = [
        (0, "No scaling"),
        (2, "Scale=2"),
        (7, "Scale=7 (common)"),
        (14, "Scale=14 (maximum)"),
    ]
    print(f"  {'Scale':>6}  {'Raw window':>10}  {'Actual window':>15}  {'Note':>25}")
    for shift, label in configs:
        ws = WindowScale(shift=shift)
        raw = 65535
        actual = ws.actual_window(raw)
        max_w = ws.max_window()
        note = f"max={max_w/1024/1024:.1f}MB" if shift >= 7 else f"max={max_w/1024:.0f}KB"
        print(f"  {shift:6d}  {raw:10d}  {actual:15d}  {note:>25}")
    print()
    print("  For 1-Gbps x 40ms RTT, BDP = 5MB. Need scale >= 7 (65535*128 = 8MB).")

    print()
    print("=" * 70)
    print("LFN Problem 3: Bandwidth-Delay Product Analysis")
    print("=" * 70)
    scenarios = [
        ("Transcontinental 1G", 1000, 40),
        ("Satellite GEO", 50, 500),
        ("Transcontinental 10G", 10000, 40),
        ("Cross-country 40G", 40000, 30),
    ]
    print(f"  {'Scenario':>25}  {'BW(Mbps)':>8}  {'RTT(ms)':>7}  {'BDP(MB)':>8}  {'64KB enough?':>13}")
    for name, bw, rtt in scenarios:
        bdp_bits = bw * 1e6 * rtt / 1000
        bdp_mb = bdp_bits / 8 / 1e6
        enough = "YES" if bdp_mb < 0.064 else "NO"
        print(f"  {name:>25}  {bw:8.0f}  {rtt:7.0f}  {bdp_mb:8.1f}  {enough:>13}")
    print()
    print("  LFNs require: large windows (scaling), PAWS, selective repeat (not go-back-N).")

    print()
    print("=" * 70)
    print("DTN Architecture: Store-Carry-Forward (Sec 6.7.1, Fig 6-56)")
    print("=" * 70)
    net = DTNNetwork()
    source = net.add_node("Source")
    node1 = net.add_node("Airplane")
    node2 = net.add_node("GroundStation")
    dest = net.add_node("Destination")

    print("  Creating bundles at source:")
    for i in range(3):
        b = Bundle(id=f"IMG-{i}", source="Source", destination="Destination",
                   payload=f"image data {i}".encode() * 100, lifetime=7200,
                   custodian="Source", creation_time=float(i))
        source.receive_bundle(b)

    print()
    print("  Contact 1: Source -> Airplane (satellite uplink, 8 Mbps, 10 min)")
    net.simulate_contact("Source", "Airplane", bw_kbps=8000, duration_s=600)

    print()
    print("  Airplane flies (store-carry)... no contact for 2 hours")
    print(f"  Airplane storage: {len(node1.storage)} bundles")

    print()
    print("  Contact 2: Airplane -> GroundStation (downlink, 8 Mbps, 14 min)")
    net.simulate_contact("Airplane", "GroundStation", bw_kbps=8000, duration_s=840)

    print()
    print("  Contact 3: GroundStation -> Destination (terrestrial, 100 Mbps)")
    net.simulate_contact("GroundStation", "Destination", bw_kbps=100000, duration_s=10)

    print()
    print(f"  Final state:")
    for name, node in net.nodes.items():
        print(f"    {name}: {len(node.storage)} bundles in storage")

    print()
    print("  Key DTN concepts demonstrated:")
    print("  - Store-carry-forward: bundles stored for hours during flight")
    print("  - Intermittent contacts: links work only during pass windows")
    print("  - Custody transfer: custodian changed as bundles move between nodes")
    print("  - Decoupled links: satellite downlink not limited by terrestrial speed")


if __name__ == "__main__":
    main()