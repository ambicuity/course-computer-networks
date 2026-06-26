#!/usr/bin/env python3
"""RSVP / Integrated Services simulator.

Models the IntServ control plane: PATH messages travel downstream,
RESV messages travel upstream, each router runs admission control
against the free capacity of its outgoing interface.

Run:  python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple


class FlowID(NamedTuple):
    src: str
    dst: str
    proto: str
    src_port: int
    dst_port: int


@dataclass(frozen=True)
class TSpec:
    rate: float
    bucket: float
    peak: float
    max_pkt: int


@dataclass(frozen=True)
class RSpec:
    service: str
    rate: float
    slack: float


@dataclass(frozen=True)
class Flowspec:
    tspec: TSpec
    rspec: RSpec


@dataclass
class PathState:
    prev_hop: str
    tspec: TSpec


@dataclass
class Reservation:
    flow: FlowID
    spec: Flowspec
    prev_hop: str
    next_hop: str


@dataclass
class Interface:
    name: str
    capacity: float
    reservations: dict[FlowID, float] = field(default_factory=dict)

    @property
    def free(self) -> float:
        return self.capacity - sum(self.reservations.values())

    def admit(self, flow: FlowID, rate: float) -> bool:
        if rate > self.free + 1e-9:
            return False
        self.reservations[flow] = max(self.reservations.get(flow, 0.0), rate)
        return True

    def release(self, flow: FlowID) -> None:
        self.reservations.pop(flow, None)


@dataclass
class Router:
    name: str
    interfaces: dict[str, Interface] = field(default_factory=dict)
    path_state: dict[FlowID, PathState] = field(default_factory=dict)
    reservations: dict[FlowID, Reservation] = field(default_factory=dict)

    def note(self, msg: str) -> None:
        print(f"  [{self.name}] {msg}")


LINKS: list[tuple[str, str, str, float]] = [
    ("S1", "R1", "if0", 10_000.0),
    ("R1", "R2", "if1", 1_000.0),
    ("R2", "R3", "if2", 2_000.0),
    ("R3", "Rcv5", "if3", 10_000.0),
    ("R2", "Rcv3", "if4", 10_000.0),
]

IFACE_MAP = {
    ("S1", "R1"): "if0",
    ("R1", "R2"): "if1",
    ("R2", "R3"): "if2",
    ("R3", "Rcv5"): "if3",
    ("R2", "Rcv3"): "if4",
}


def build_topology() -> dict[str, Router]:
    routers: dict[str, Router] = {}
    for src, dst, iface, cap in LINKS:
        routers.setdefault(src, Router(src))
        routers.setdefault(dst, Router(dst))
        r = routers[src]
        if iface not in r.interfaces:
            r.interfaces[iface] = Interface(iface, cap)
    return routers


def iface_to(routers: dict[str, Router], src: str, dst: str) -> Interface:
    return routers[src].interfaces[IFACE_MAP[(src, dst)]]


def send_path(
    routers: dict[str, Router], path: list[str], flow: FlowID, tspec: TSpec
) -> None:
    print(f"PATH  {flow.src} -> {flow.dst}  (TSpec r={tspec.rate} b={tspec.bucket})")
    for i in range(len(path) - 1):
        hop = path[i]
        r = routers[hop]
        prev = path[i - 1] if i > 0 else "<sender>"
        r.path_state[flow] = PathState(prev_hop=prev, tspec=tspec)
        r.note(f"PATH installed: prev_hop={prev}, tspec.rate={tspec.rate}")


def send_resv(
    routers: dict[str, Router], path: list[str], flow: FlowID, spec: Flowspec
) -> bool:
    print(f"RESV  {flow.dst} -> {flow.src}  (service={spec.rspec.service} R={spec.rspec.rate})")
    admitted_hops: list[tuple[str, str]] = []
    admitted = True
    for i in range(len(path) - 1, 0, -1):
        hop, prev = path[i], path[i - 1]
        upstream = routers[prev]
        if prev == path[0]:
            upstream.note(f"RESV reached sender {prev}; reservation complete")
            continue
        iface = iface_to(routers, prev, hop)
        rate = spec.rspec.rate
        if iface.admit(flow, rate):
            upstream.reservations[flow] = Reservation(
                flow=flow, spec=spec,
                prev_hop=path[i - 2] if i - 2 >= 0 else "<sender>",
                next_hop=hop,
            )
            admitted_hops.append((prev, iface.name))
            upstream.note(f"RESV admitted on {iface.name}: free={iface.free:.0f}/{iface.capacity:.0f} kbps")
        else:
            upstream.note(f"RESVERR on {iface.name}: need {rate:.0f}, free {iface.free:.0f}")
            admitted = False
            for rb_name, rb_iface in admitted_hops:
                rb_r = routers[rb_name]
                rb_r.interfaces[rb_iface].release(flow)
                rb_r.reservations.pop(flow, None)
                rb_r.note(f"RESVERR rollback: released {flow.dst_port} on {rb_iface}")
            break
    return admitted


def main() -> None:
    print("=" * 72)
    print(" Integrated Services / RSVP simulator")
    print("=" * 72)
    routers = build_topology()

    flow_a = FlowID("S1", "Rcv3", "UDP", 5004, 5004)
    spec_a = Flowspec(
        TSpec(rate=64.0, bucket=8.0, peak=96.0, max_pkt=200),
        RSpec(service="controlled-load", rate=64.0, slack=0.0),
    )
    path_a = ["S1", "R1", "R2", "Rcv3"]
    send_path(routers, path_a, flow_a, spec_a.tspec)
    print(f"  -> Flow A admitted: {send_resv(routers, path_a, flow_a, spec_a)}\n")

    flow_b = FlowID("S1", "Rcv5", "UDP", 5006, 5006)
    spec_b = Flowspec(
        TSpec(rate=500.0, bucket=64.0, peak=800.0, max_pkt=1500),
        RSpec(service="guaranteed", rate=500.0, slack=20.0),
    )
    path_b = ["S1", "R1", "R2", "R3", "Rcv5"]
    send_path(routers, path_b, flow_b, spec_b.tspec)
    print(f"  -> Flow B admitted: {send_resv(routers, path_b, flow_b, spec_b)}\n")

    flow_c = FlowID("S1", "Rcv5", "UDP", 5008, 5008)
    spec_c = Flowspec(
        TSpec(rate=600.0, bucket=80.0, peak=900.0, max_pkt=1500),
        RSpec(service="guaranteed", rate=600.0, slack=10.0),
    )
    send_path(routers, path_b, flow_c, spec_c.tspec)
    print(f"  -> Flow C admitted: {send_resv(routers, path_b, flow_c, spec_c)}\n")

    print("=" * 72)
    print(" Per-router state summary")
    print("=" * 72)
    for name in ("R1", "R2", "R3"):
        r = routers[name]
        print(f"\nRouter {name}: path_state={len(r.path_state)} reservations={len(r.reservations)}")
        for fid, res in r.reservations.items():
            print(f"  {fid.dst_port}: {res.spec.rspec.service} R={res.spec.rspec.rate:.0f} kbps")
        for iname, iface in r.interfaces.items():
            used = iface.capacity - iface.free
            print(f"  {iname}: {used:.0f}/{iface.capacity:.0f} kbps ({len(iface.reservations)} flows)")
    print("\nDone. Exit 0.")


if __name__ == "__main__":
    main()