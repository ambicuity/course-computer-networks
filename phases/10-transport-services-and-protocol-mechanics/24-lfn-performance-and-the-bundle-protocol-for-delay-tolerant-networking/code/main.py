#!/usr/bin/env python3
"""LFN performance and Bundle Protocol simulator.

Computes bandwidth-delay products and minimum windows for long-fat
networks, sequence-number wrap times, and a tiny Bundle Protocol
primary-block encoder. Simulates a three-node DTN with intermittent
contacts.

No network calls, no third-party packages -- pure stdlib so it runs
anywhere with `python3 main.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_SEQ_NUMBER = 1 << 32
MSL_SECONDS = 120.0
SECONDS_PER_DAY = 86400.0


@dataclass(frozen=True)
class Contact:
    src: str
    dst: str
    start_sec: float
    duration_sec: float
    bandwidth_bps: float

    @property
    def end_sec(self) -> float:
        return self.start_sec + self.duration_sec


@dataclass
class Bundle:
    src: str
    dst: str
    size_bytes: int
    created_sec: float
    location: str
    delivered_sec: float | None = None

    def remaining_bytes(self) -> int:
        return 0 if self.delivered_sec is not None else self.size_bytes


@dataclass
class DtnNode:
    name: str
    bundles: list[Bundle] = field(default_factory=list)

    def receive(self, bundle: Bundle, at_sec: float) -> None:
        bundle.location = self.name
        self.bundles.append(bundle)
        print(
            f"   t={at_sec:>6.1f}s  {self.name} received bundle "
            f"({bundle.size_bytes} B) from {bundle.src}"
        )


def lfn_throughput(bandwidth_bps: int, rtt_seconds: float) -> dict[str, float]:
    bits = bandwidth_bps * rtt_seconds
    return {
        "bandwidth_bps": bandwidth_bps,
        "rtt_seconds": rtt_seconds,
        "bdp_bytes": bits / 8.0,
        "minimum_window_bytes": int(bits / 8.0),
        "tcp_throughput_with_64k_window_bps": (65535 * 8) / rtt_seconds,
    }


def wrap_time(bandwidth_bps: int) -> float:
    return MAX_SEQ_NUMBER * 8 / bandwidth_bps


def paws_required(bandwidth_bps: int, msl_seconds: float = MSL_SECONDS) -> bool:
    return wrap_time(bandwidth_bps) < msl_seconds


def frame_efficiency(link_mtu: int, mss_bytes: int) -> float:
    return mss_bytes / link_mtu


def bundle_header(
    version: int,
    destination_uri: str,
    source_uri: str,
    custodian_uri: str,
    lifetime_seconds: int,
) -> bytes:
    """Tiny stand-in for an RFC 5050/9171 primary block."""
    header = bytearray()
    header.append(version & 0xFF)
    header.extend((0).to_bytes(2, "big"))  # flags
    header.extend(_sdnv(len(destination_uri)))
    header.extend(destination_uri.encode())
    header.extend(_sdnv(len(source_uri)))
    header.extend(source_uri.encode())
    header.extend(_sdnv(len(custodian_uri)))
    header.extend(custodian_uri.encode())
    header.extend(_sdnv(0))  # report-to (none)
    header.extend(_sdnv(0))  # creation timestamp
    header.extend(_sdnv(lifetime_seconds))
    header.extend(b"\x00")  # dictionary length
    return bytes(header)


def _sdnv(value: int) -> bytes:
    """Self-Delimiting Numeric Value encoding used in RFC 5050."""
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def dtn_simulator(
    nodes: dict[str, DtnNode],
    contacts: list[Contact],
    bundles_to_send: list[Bundle],
) -> dict[str, float]:
    """Track bundles across contacts; report delivery time per destination."""
    delivered_at: dict[str, float] = {}
    pending = list(bundles_to_send)
    in_flight: list[Bundle] = []
    timeline_end = max((c.end_sec for c in contacts), default=0.0)
    dt = 1.0
    t = 0.0
    while t <= timeline_end and pending:
        active = [c for c in contacts if c.start_sec <= t < c.end_sec]
        for contact in active:
            for bundle in list(pending) + list(in_flight):
                if bundle.location != contact.src:
                    continue
                transfer_rate = contact.bandwidth_bps / 8.0 * dt
                bundle.size_bytes -= int(transfer_rate)
                if bundle.size_bytes <= 0:
                    nodes[contact.dst].receive(bundle, at_sec=t)
                    pending.remove(bundle) if bundle in pending else in_flight.remove(bundle)
                    delivered_at[bundle.dst] = t
        in_flight = [b for b in in_flight if b.size_bytes > 0]
        in_flight += [b for b in pending if any(c.dst == b.location for c in active)]
        t += dt
    return delivered_at


def main() -> None:
    print("=" * 70)
    print("LFN PERFORMANCE + BUNDLE PROTOCOL  --  long fat networks and DTN")
    print("=" * 70)

    print("\n[1] Bandwidth-delay products and minimum window:")
    paths = [
        ("Geostationary 50 Mbps / 540 ms", 50_000_000, 0.540),
        ("Transcontinental 1 Gbps / 40 ms", 1_000_000_000, 0.040),
        ("Transcontinental 10 Gbps / 80 ms", 10_000_000_000, 0.080),
        ("Earth-Mars 6 Mbps / 20 min RTT", 6_000_000, 20 * 60),
        ("100 Gbps R&D link / 100 ms RTT", 100_000_000_000, 0.100),
    ]
    for label, bw, rtt in paths:
        result = lfn_throughput(bw, rtt)
        legacy = result["tcp_throughput_with_64k_window_bps"]
        print(
            f"   {label:<35}  BD product = {result['bdp_bytes']:>16,.0f} B   "
            f"min window = {result['minimum_window_bytes']:>13,} B"
        )
        print(
            f"      legacy 64KB window caps throughput at {legacy / 1e6:>7.2f} Mbps "
            f"(vs {bw / 1e6:>6.0f} Mbps link)"
        )

    print("\n[2] Sequence-number wrap time and PAWS requirement:")
    for label, bw, _ in paths:
        wt = wrap_time(bw)
        paws = paws_required(bw)
        print(
            f"   {label:<35}  wrap = {wt:>10,.1f} s ({wt / 3600:>6.2f} h)   "
            f"PAWS needed: {paws}"
        )

    print("\n[3] Jumbo frame efficiency vs standard Ethernet:")
    for mtu in (1500, 9000):
        eff = frame_efficiency(mtu, mtu - 40)
        print(f"   MTU={mtu:<5}  MSS={mtu - 40:<5}  payload efficiency = {eff * 100:.2f}%")

    print("\n[4] Bundle Protocol primary block (RFC 5050/9171) -- minimal sample:")
    raw = bundle_header(
        version=7,
        destination_uri="dtn://server/bundle",
        source_uri="dtn://client/bundle",
        custodian_uri="dtn://client/bundle",
        lifetime_seconds=3600,
    )
    print(f"   raw ({len(raw)} bytes): {raw.hex()}")
    print("   fields:")
    print("     version        = 7 (RFC 9171)")
    print("     flags          = 0 (no class-of-service / custody bit set)")
    print("     destination    = dtn://server/bundle")
    print("     source         = dtn://client/bundle")
    print("     custodian      = dtn://client/bundle")
    print("     report-to      = (none)")
    print("     lifetime       = 3600 s (1 hour)")

    print("\n[5] DTN simulator -- three nodes A-B-C with intermittent contacts:")
    nodes = {"A": DtnNode("A"), "B": DtnNode("B"), "C": DtnNode("C")}
    contacts = [
        Contact("A", "B", start_sec=0.0, duration_sec=60.0, bandwidth_bps=10_000_000),
        Contact("B", "C", start_sec=30.0, duration_sec=60.0, bandwidth_bps=10_000_000),
    ]
    initial_bundle = Bundle(
        src="A", dst="C", size_bytes=10_000_000, created_sec=0.0, location="A"
    )
    delivery = dtn_simulator(nodes, contacts, [initial_bundle])
    print(f"   delivered to C at t = {delivery.get('C', float('inf'))}s")
    print("   path: A -> (A-B contact at t=0..60s) -> B -> (B-C contact at t=30..90s) -> C")

    print("\n[6] Earth-Mars TCP round-trip ignores end-to-end assumption:")
    mars_rtt = 20 * 60
    mars_file_mb = 1
    bytes_in_pipe = 6_000_000 * mars_rtt / 8
    print(f"   bytes in flight at any moment = {bytes_in_pipe / 1e6:.1f} MB")
    print(f"   TCP retransmit lost segments one RTT later = {mars_rtt} s wait")
    print("   Bundle Protocol over LTP -- sends once, never retransmits, accepts best-effort delivery")

    print("\nDone. The two regimes use the same data but very different transport semantics.")


if __name__ == "__main__":
    main()