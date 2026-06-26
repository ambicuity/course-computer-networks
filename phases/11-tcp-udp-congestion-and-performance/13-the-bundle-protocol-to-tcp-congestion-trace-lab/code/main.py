#!/usr/bin/env python3
"""Bundle protocol simulator and TCP congestion trace analyzer.

Stdlib only. Demonstrates Sec 6.7.2 (The Bundle Protocol) and a TCP
congestion trace lab (analyzing cwnd evolution from a packet trace):

1. Bundle protocol message format: primary block (version, flags, dest,
   source, custodian, report-to, creation timestamp, lifetime, dictionary)
   and payload block (type, flags, length, data).
2. Custody transfer: the custodian field changes as bundles move through
   DTN nodes, with custody acknowledgment.
3. TCP congestion trace analyzer: parse a text trace of cwnd/ssthresh
   values over RTT rounds, identify slow-start vs congestion-avoidance
   phases, detect fast-retransmit and timeout events, and compute
   statistics (peak cwnd, average, number of reductions).

Run:  python3 main.py
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Part 1: Bundle Protocol (RFC 5050)
# ---------------------------------------------------------------------------

BUNDLE_VERSION = 6

COS_BULK = 0x00
COS_NORMAL = 0x01
COS_EXPEDITED = 0x02
COS_RESERVED = 0x03

FLAG_CUSTODY_REQUESTED = 0x01
FLAG_DESTINATION_ACK = 0x02
FLAG_SOURCE_REPORT = 0x04


@dataclass
class PrimaryBlock:
    version: int = BUNDLE_VERSION
    flags: int = COS_NORMAL
    dest_eid: str = ""
    source_eid: str = ""
    custodian_eid: str = ""
    report_to_eid: str = ""
    creation_time: int = 0
    sequence_number: int = 0
    lifetime: int = 3600
    fragment_offset: int = 0
    total_length: int = 0

    def encode(self) -> bytes:
        eid_table = [self.dest_eid, self.source_eid, self.custodian_eid, self.report_to_eid]
        dictionary = "\x00".join(eid_table).encode()
        encoded = struct.pack("!BB", self.version, self.flags)
        encoded += struct.pack("!H", len(dictionary))
        encoded += dictionary
        encoded += struct.pack("!III", self.creation_time, self.sequence_number, self.lifetime)
        return encoded

    @classmethod
    def decode(cls, raw: bytes) -> "PrimaryBlock":
        version, flags = struct.unpack("!BB", raw[:2])
        dict_len = struct.unpack("!H", raw[2:4])[0]
        dictionary = raw[4:4+dict_len].decode()
        eids = dictionary.split("\x00")
        ct, sn, lt = struct.unpack("!III", raw[4+dict_len:4+dict_len+12])
        return cls(
            version=version, flags=flags,
            dest_eid=eids[0] if len(eids) > 0 else "",
            source_eid=eids[1] if len(eids) > 1 else "",
            custodian_eid=eids[2] if len(eids) > 2 else "",
            report_to_eid=eids[3] if len(eids) > 3 else "",
            creation_time=ct, sequence_number=sn, lifetime=lt,
        )

    def __str__(self) -> str:
        cos = {0: "BULK", 1: "NORMAL", 2: "EXPEDITED"}.get(self.flags & 0x03, "?")
        custody = "CUSTODY" if self.flags & FLAG_CUSTODY_REQUESTED else "no-custody"
        ack = "ACK" if self.flags & FLAG_DESTINATION_ACK else "no-ack"
        return (f"V{self.version} cos={cos} {custody} {ack} "
                f"src={self.source_eid} dst={self.dest_eid} "
                f"custodian={self.custodian_eid} lifetime={self.lifetime}s")


@dataclass
class PayloadBlock:
    type_code: int = 1
    flags: int = 0
    data: bytes = b""

    def encode(self) -> bytes:
        encoded = struct.pack("!BB", self.type_code, self.flags)
        encoded += struct.pack("!I", len(self.data))
        encoded += self.data
        return encoded

    @classmethod
    def decode(cls, raw: bytes) -> "PayloadBlock":
        tc, fl = struct.unpack("!BB", raw[:2])
        length = struct.unpack("!I", raw[2:6])[0]
        data = raw[6:6+length]
        return cls(type_code=tc, flags=fl, data=data)


@dataclass
class BundleMessage:
    primary: PrimaryBlock
    payload: PayloadBlock

    def encode(self) -> bytes:
        return self.primary.encode() + self.payload.encode()

    @classmethod
    def decode(cls, raw: bytes) -> "BundleMessage":
        primary = PrimaryBlock.decode(raw)
        remaining = raw[len(primary.encode()):]
        payload = PayloadBlock.decode(remaining)
        return cls(primary=primary, payload=payload)

    def __str__(self) -> str:
        return f"{self.primary} payload={len(self.payload.data)}B"


@dataclass
class DTNBundleAgent:
    eid: str
    bundles: list[BundleMessage] = field(default_factory=list)
    custody_bundles: dict[str, BundleMessage] = field(default_factory=dict)

    def send_bundle(self, dest: str, data: bytes, custodian: str = "",
                    flags: int = COS_NORMAL | FLAG_CUSTODY_REQUESTED) -> BundleMessage:
        primary = PrimaryBlock(
            flags=flags,
            dest_eid=dest, source_eid=self.eid,
            custodian_eid=custodian or self.eid,
            report_to_eid=self.eid,
            creation_time=1000, sequence_number=len(self.bundles),
            lifetime=3600,
        )
        payload = PayloadBlock(data=data)
        msg = BundleMessage(primary=primary, payload=payload)
        self.bundles.append(msg)
        return msg

    def accept_custody(self, msg: BundleMessage) -> None:
        msg.primary.custodian_eid = self.eid
        self.custody_bundles[msg.primary.sequence_number] = msg

    def forward(self, msg: BundleMessage, peer: "DTNBundleAgent") -> None:
        peer.accept_custody(msg)
        print(f"    [{self.eid}] -> [{peer.eid}]: custody transferred for bundle "
              f"seq={msg.primary.sequence_number}")


# ---------------------------------------------------------------------------
# Part 2: TCP Congestion Trace Analyzer
# ---------------------------------------------------------------------------

@dataclass
class TraceSample:
    rtt: int
    cwnd: int
    ssthresh: int
    event: str

    def __str__(self) -> str:
        return f"RTT={self.rtt:3d} cwnd={self.cwnd:4d} ssthresh={self.ssthresh:5d} {self.event}"


def generate_tahoe_trace() -> list[TraceSample]:
    """Generate a TCP Tahoe trace (Fig 6-46): slow start, cong. avoid, loss."""
    trace: list[TraceSample] = []
    cwnd = 1
    ssthresh = 32
    for rtt in range(0, 13):
        if cwnd < ssthresh:
            event = "slow start"
        else:
            event = "cong. avoid"
        trace.append(TraceSample(rtt, cwnd, ssthresh, event))
        if cwnd < ssthresh:
            cwnd *= 2
        else:
            cwnd += 1
    trace.append(TraceSample(13, cwnd, ssthresh, "3 DUP ACK -> loss detected"))
    ssthresh = max(cwnd // 2, 2)
    cwnd = 1
    for rtt in range(14, 24):
        if cwnd < ssthresh:
            event = "slow start (recovery)"
        else:
            event = "cong. avoid"
        trace.append(TraceSample(rtt, cwnd, ssthresh, event))
        if cwnd < ssthresh:
            cwnd *= 2
        else:
            cwnd += 1
    return trace


def generate_reno_trace() -> list[TraceSample]:
    """Generate a TCP Reno trace (Fig 6-47): sawtooth pattern."""
    trace: list[TraceSample] = []
    cwnd = 1
    ssthresh = 32
    for rtt in range(0, 8):
        event = "slow start" if cwnd < ssthresh else "cong. avoid"
        trace.append(TraceSample(rtt, cwnd, ssthresh, event))
        cwnd = cwnd * 2 if cwnd < ssthresh else cwnd + 1
    for cycle in range(3):
        cwnd = ssthresh
        for rtt in range(8 + cycle * 8, 8 + (cycle + 1) * 8):
            event = "cong. avoid (additive increase)"
            trace.append(TraceSample(rtt, cwnd, ssthresh, event))
            cwnd += 1
        ssthresh = max(cwnd // 2, 2)
        trace.append(TraceSample(8 + (cycle + 1) * 8, cwnd, ssthresh,
                                 "3 DUP ACK -> fast retransmit/recovery"))
    return trace


def analyze_trace(trace: list[TraceSample]) -> dict[str, object]:
    cwnds = [s.cwnd for s in trace]
    peak = max(cwnds)
    avg = sum(cwnds) / len(cwnds)
    slow_start_count = sum(1 for s in trace if "slow start" in s.event)
    cong_avoid_count = sum(1 for s in trace if "cong. avoid" in s.event)
    loss_events = [s for s in trace if "loss" in s.event or "fast retransmit" in s.event]
    reductions = len(loss_events)
    return {
        "peak_cwnd": peak,
        "avg_cwnd": round(avg, 1),
        "slow_start_rtts": slow_start_count,
        "cong_avoid_rtts": cong_avoid_count,
        "loss_events": reductions,
        "loss_details": [str(s) for s in loss_events],
    }


def detect_phases(trace: list[TraceSample]) -> list[tuple[int, int, str]]:
    """Identify continuous phases: (start_rtt, end_rtt, phase_name)."""
    phases: list[tuple[int, int, str]] = []
    if not trace:
        return phases
    start = trace[0].rtt
    current_phase = trace[0].event
    for s in trace[1:]:
        if s.event != current_phase:
            phases.append((start, s.rtt - 1, current_phase))
            start = s.rtt
            current_phase = s.event
    phases.append((start, trace[-1].rtt, current_phase))
    return phases


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("Bundle Protocol: Primary Block + Payload Block (Fig 6-59)")
    print("=" * 70)
    agent = DTNBundleAgent(eid="dtn://source.dtn")
    peer = DTNBundleAgent(eid="dtn://groundstation.dtn")
    final = DTNBundleAgent(eid="dtn://destination.dtn")

    print("  Source creates a bundle:")
    msg = agent.send_bundle("dtn://destination.dtn", b"Earth image data block 1" * 10,
                            custodian="dtn://source.dtn",
                            flags=COS_EXPEDITED | FLAG_CUSTODY_REQUESTED | FLAG_DESTINATION_ACK)
    print(f"  {msg}")
    encoded = msg.encode()
    print(f"  Encoded: {len(encoded)} bytes total")
    print(f"    Primary block: {len(msg.primary.encode())} bytes")
    print(f"    Payload block: {len(msg.payload.encode())} bytes (data={len(msg.payload.data)}B)")

    print()
    print("  Round-trip decode:")
    decoded = BundleMessage.decode(encoded)
    print(f"  {decoded}")
    print(f"  Primary: version={decoded.primary.version} flags=0x{decoded.primary.flags:02X}")
    print(f"    dest={decoded.primary.dest_eid}")
    print(f"    source={decoded.primary.source_eid}")
    print(f"    custodian={decoded.primary.custodian_eid}")
    print(f"    creation_time={decoded.primary.creation_time} seq={decoded.primary.sequence_number}")
    print(f"    lifetime={decoded.primary.lifetime}s")
    print(f"  Payload: type={decoded.payload.type_code} data_len={len(decoded.payload.data)}")
    print(f"  Data matches: {decoded.payload.data == msg.payload.data}")

    print()
    print("=" * 70)
    print("Custody Transfer: Bundles Move Through DTN Nodes")
    print("=" * 70)
    print("  Step 1: Source -> GroundStation (custody transfer)")
    agent.forward(msg, peer)
    print(f"  New custodian: {peer.custody_bundles[msg.primary.sequence_number].primary.custodian_eid}")

    msg2 = agent.send_bundle("dtn://destination.dtn", b"Earth image data block 2" * 10)
    print()
    print("  Step 2: GroundStation -> Destination (custody transfer)")
    peer.forward(msg, final)
    print(f"  New custodian: {final.custody_bundles[msg.primary.sequence_number].primary.custodian_eid}")

    print()
    print("  Custody chain: Source -> GroundStation -> Destination")
    print("  Each node assumes responsibility for delivery. If a link fails,")
    print("  the current custodian retransmits when a new contact appears.")

    print()
    print("=" * 70)
    print("TCP Congestion Trace Lab: TCP Tahoe (Fig 6-46)")
    print("=" * 70)
    tahoe = generate_tahoe_trace()
    print(f"  {'RTT':>4}  {'cwnd':>6}  {'ssthresh':>8}  {'event':>30}")
    for s in tahoe:
        print(f"  {s.rtt:4d}  {s.cwnd:6d}  {s.ssthresh:8d}  {s.event:>30}")

    print()
    stats = analyze_trace(tahoe)
    print(f"  Analysis:")
    print(f"    Peak cwnd:       {stats['peak_cwnd']}")
    print(f"    Average cwnd:    {stats['avg_cwnd']}")
    print(f"    Slow start RTTs: {stats['slow_start_rtts']}")
    print(f"    Cong avoid RTTs: {stats['cong_avoid_rtts']}")
    print(f"    Loss events:     {stats['loss_events']}")
    for detail in stats["loss_details"]:
        print(f"      {detail}")

    phases = detect_phases(tahoe)
    print(f"  Phases detected:")
    for start, end, name in phases:
        print(f"    RTT {start:2d}-{end:2d}: {name}")

    print()
    print("=" * 70)
    print("TCP Congestion Trace Lab: TCP Reno Sawtooth (Fig 6-47)")
    print("=" * 70)
    reno = generate_reno_trace()
    print(f"  {'RTT':>4}  {'cwnd':>6}  {'ssthresh':>8}  {'event':>35}")
    for s in reno:
        print(f"  {s.rtt:4d}  {s.cwnd:6d}  {s.ssthresh:8d}  {s.event:>35}")

    print()
    stats_r = analyze_trace(reno)
    print(f"  Analysis:")
    print(f"    Peak cwnd:       {stats_r['peak_cwnd']}")
    print(f"    Average cwnd:    {stats_r['avg_cwnd']}")
    print(f"    Slow start RTTs: {stats_r['slow_start_rtts']}")
    print(f"    Cong avoid RTTs: {stats_r['cong_avoid_rtts']}")
    print(f"    Loss events:     {stats_r['loss_events']}")

    print()
    print("  Reno vs Tahoe difference:")
    print("  Tahoe: after loss, cwnd=1 -> slow start from scratch")
    print("  Reno:  after loss, cwnd=ssthresh -> skip slow start (fast recovery)")
    print("  Reno produces the classic sawtooth: linear up, halve down.")


if __name__ == "__main__":
    main()