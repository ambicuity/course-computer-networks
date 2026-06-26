"""802.11 architecture simulator.

Lesson 18 -- 802.11 architecture: infrastructure vs ad hoc, AP, BSS, ESS, DS.

This module is stdlib-only. It models:

  * a BSS, an AP, and a Station as immutable dataclasses
  * the scan -> authenticate -> associate state machine
  * ESS routing across a wired Distribution System
  * an IBSS (ad hoc) peer-to-peer BSS with no AP
  * 2.4 GHz channel overlap (1/6/11 are non-overlapping)

Run with: python3 code/main.py
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable


# ---------------------------------------------------------------------------
# Constants and types
# ---------------------------------------------------------------------------


PHY_FLAVORS: tuple[tuple[str, int, str, str, int], ...] = (
    ("legacy DSSS", 1997, "2.4 GHz", "DSSS", 2),
    ("802.11b", 1999, "2.4 GHz", "DSSS+CCK", 11),
    ("802.11a", 1999, "5 GHz", "OFDM", 54),
    ("802.11g", 2003, "2.4 GHz", "OFDM", 54),
    ("802.11n", 2009, "2.4/5 GHz", "MIMO-OFDM", 600),
)


class StaState(str, Enum):
    """802.11 station association state machine (LCI)."""

    UNAUTHENTICATED = "UNAUTHENTICATED"
    AUTHENTICATED = "AUTHENTICATED"
    ASSOCIATED = "ASSOCIATED"
    REASSOCIATED = "REASSOCIATED"


# ---------------------------------------------------------------------------
# Topology primitives
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Channel:
    """A 2.4 or 5 GHz channel number; 0 means DFS-5GHz, ignored for overlap."""

    number: int
    band_ghz: float = 2.4

    def __post_init__(self) -> None:
        if not 0 <= self.number <= 165:
            raise ValueError(f"channel {self.number} is not a legal Wi-Fi channel")

    def label(self) -> str:
        return f"ch{self.number}@{self.band_ghz}GHz"


@dataclass(frozen=True)
class BSSID:
    """48-bit BSS identifier. For infrastructure mode this is the AP's MAC."""

    octets: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.octets) != 6:
            raise ValueError("BSSID must be 6 bytes")
        if not all(0 <= b <= 255 for b in self.octets):
            raise ValueError("BSSID bytes must be 0..255")

    @classmethod
    def from_ap_mac(cls, ap_mac: str) -> "BSSID":
        return cls(tuple(int(x, 16) for x in ap_mac.split(":")))

    @classmethod
    def random_ibss(cls, rng: random.Random) -> "BSSID":
        # Local bit (bit 1 of first byte) set, multicast bit (bit 0) set.
        first = (rng.randint(0, 0xFF) | 0x03) & 0xFF
        rest = tuple(rng.randint(0, 0xFF) for _ in range(5))
        return cls((first, *rest))

    def mac_str(self) -> str:
        return ":".join(f"{b:02x}" for b in self.octets)


@dataclass(frozen=True)
class AccessPoint:
    """A bridge between one BSS and the wired Distribution System."""

    bssid: BSSID
    ssid: str
    channel: Channel
    ds_port: str  # symbolic uplink into the DistributionSystem

    def label(self) -> str:
        return f"AP[{self.bssid.mac_str()} ssid={self.ssid!r} {self.channel.label()}]"


@dataclass(frozen=True)
class Station:
    """A wireless client. Identity is the MAC; membership is the state."""

    mac: str
    state: StaState = StaState.UNAUTHENTICATED
    associated_bssid: BSSID | None = None

    def with_state(self, new_state: StaState, bssid: BSSID | None) -> "Station":
        return replace(self, state=new_state, associated_bssid=bssid)


@dataclass(frozen=True)
class BSS:
    """Basic Service Set: one AP and a snapshot of associated stations."""

    ap: AccessPoint
    stations: tuple[Station, ...] = ()

    def with_station(self, sta: Station) -> "BSS":
        existing = [s for s in self.stations if s.mac != sta.mac]
        existing.append(sta)
        return replace(self, stations=tuple(existing))

    def find_sta(self, mac: str) -> Station | None:
        for s in self.stations:
            if s.mac == mac:
                return s
        return None


# ---------------------------------------------------------------------------
# Channel overlap (2.4 GHz: 1, 6, 11 are non-overlapping)
# ---------------------------------------------------------------------------


def channels_overlap(a: Channel, b: Channel) -> bool:
    """Two 2.4 GHz channels overlap unless they are the standard 1/6/11 set."""

    if a.band_ghz != 2.4 or b.band_ghz != 2.4:
        return a.number == b.number  # 5 GHz: only same-number collides
    diff = abs(a.number - b.number)
    # Each 2.4 GHz channel is 22 MHz wide; 5-channel spacing guarantees non-overlap.
    return diff < 5


# ---------------------------------------------------------------------------
# Distribution System
# ---------------------------------------------------------------------------


@dataclass
class DistributionSystem:
    """Wired backhaul linking APs. Records every frame that crosses it."""

    name: str
    forwarding_table: dict[str, str] = field(default_factory=dict)
    log: list[tuple[str, str, str]] = field(default_factory=list)

    def register(self, ap: AccessPoint) -> None:
        self.forwarding_table[ap.bssid.mac_str()] = ap.ds_port

    def forward(self, src_port: str, dst_port: str, frame: str) -> None:
        self.log.append((src_port, dst_port, frame))

    def route_to_bssid(self, bssid: str) -> str | None:
        return self.forwarding_table.get(bssid)


# ---------------------------------------------------------------------------
# Association state machine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssociationEvent:
    """A single step in the scan -> authenticate -> associate FSM."""

    frame: str  # 802.11 management frame subtype name
    src: str
    dst: str
    next_state: StaState


def associate_to_ap(sta: Station, ap: AccessPoint) -> tuple[Station, list[AssociationEvent]]:
    """Run the standard three-step association; return the new STA + trace."""

    if sta.state != StaState.UNAUTHENTICATED:
        raise ValueError(f"{sta.mac} already in state {sta.state}; cannot (re)associate from here")

    trace: list[AssociationEvent] = []

    # 1. Probe: STA scans, picks this AP, sends Probe Request and gets a Response.
    trace.append(AssociationEvent("Probe Request", sta.mac, ap.bssid.mac_str(), StaState.UNAUTHENTICATED))
    trace.append(AssociationEvent("Probe Response", ap.bssid.mac_str(), sta.mac, StaState.UNAUTHENTICATED))

    # 2. Authenticate (open system, algorithm 0).
    trace.append(AssociationEvent("Authentication (open)", sta.mac, ap.bssid.mac_str(), StaState.AUTHENTICATED))
    trace.append(AssociationEvent("Authentication (success)", ap.bssid.mac_str(), sta.mac, StaState.AUTHENTICATED))

    # 3. Associate.
    trace.append(AssociationEvent("Association Request", sta.mac, ap.bssid.mac_str(), StaState.ASSOCIATED))
    trace.append(AssociationEvent("Association Response", ap.bssid.mac_str(), sta.mac, StaState.ASSOCIATED))

    final = sta.with_state(StaState.ASSOCIATED, ap.bssid)
    return final, trace


def reassociate_to_ap(sta: Station, old_ap: AccessPoint, new_ap: AccessPoint) -> tuple[Station, list[AssociationEvent]]:
    """A station that is already ASSOCIATED roams to a new AP inside the same ESS."""

    if sta.state != StaState.ASSOCIATED or sta.associated_bssid != old_ap.bssid:
        raise ValueError(f"{sta.mac} cannot reassociate from {old_ap.bssid.mac_str()} in state {sta.state}")

    trace: list[AssociationEvent] = [
        AssociationEvent("Reassociation Request", sta.mac, new_ap.bssid.mac_str(), StaState.REASSOCIATED),
        AssociationEvent("Reassociation Response", new_ap.bssid.mac_str(), sta.mac, StaState.REASSOCIATED),
    ]
    final = sta.with_state(StaState.ASSOCIATED, new_ap.bssid)
    return final, trace


# ---------------------------------------------------------------------------
# ESS routing across the DS
# ---------------------------------------------------------------------------


@dataclass
class DsRouter:
    """Forwards a frame STA1 -> AP1 -> DS -> AP2 -> STA2 across an ESS."""

    ds: DistributionSystem
    bsstable: dict[str, BSS]  # bssid.mac_str() -> BSS

    def forward_inter_bss(self, sender: Station, receiver: Station, payload: str) -> list[str]:
        if sender.associated_bssid is None or receiver.associated_bssid is None:
            raise ValueError("both stations must be associated for ESS forwarding")
        src_bss = self.bsstable[sender.associated_bssid.mac_str()]
        dst_bss = self.bsstable[receiver.associated_bssid.mac_str()]
        src_ap = src_bss.ap
        dst_ap = dst_bss.ap
        log: list[str] = []
        # 1. STA1 -> AP1 (wireless)
        log.append(f"{sender.mac} --(wireless {src_ap.channel.label()})--> {src_ap.label()}: {payload}")
        # 2. AP1 -> DS
        self.ds.forward(src_ap.ds_port, dst_ap.ds_port, payload)
        log.append(f"{src_ap.label()} --(DS {self.ds.name})--> {dst_ap.label()}: {payload}")
        # 3. AP2 -> STA2 (wireless)
        log.append(f"{dst_ap.label()} --(wireless {dst_ap.channel.label()})--> {receiver.mac}: {payload}")
        return log


# ---------------------------------------------------------------------------
# IBSS (ad hoc) peer-to-peer BSS
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IBSS:
    """Independent BSS: no AP, BSSID is a random locally administered value."""

    bssid: BSSID
    channel: Channel
    members: tuple[Station, ...] = ()

    def with_member(self, sta: Station) -> "IBSS":
        members = tuple(s for s in self.members if s.mac != sta.mac) + (sta,)
        return replace(self, members=members)

    def forward_peer(self, sender_mac: str, receiver_mac: str, payload: str) -> list[str]:
        if not any(s.mac == sender_mac for s in self.members):
            raise ValueError(f"{sender_mac} is not a member of this IBSS")
        if not any(s.mac == receiver_mac for s in self.members):
            raise ValueError(f"{receiver_mac} is not a member of this IBSS")
        return [
            f"IBSS{self.bssid.mac_str()[-5:]} {self.channel.label()}: "
            f"{sender_mac} --(peer, no AP)--> {receiver_mac}: {payload}"
        ]


def make_random_ibss(rng: random.Random, channel: Channel) -> IBSS:
    return IBSS(bssid=BSSID.random_ibss(rng), channel=channel)


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------


def _hr(title: str) -> None:
    print()
    print("=" * 72)
    print(f" {title}")
    print("=" * 72)


def demo_association_state_machine() -> None:
    _hr("Demo 1: scan -> authenticate -> associate state machine")
    ap = AccessPoint(
        bssid=BSSID.from_ap_mac("aa:bb:cc:00:00:01"),
        ssid="LabWiFi",
        channel=Channel(1, 2.4),
        ds_port="sw0/g1",
    )
    sta = Station(mac="00:11:22:33:44:55")
    print(f"start: STA {sta.mac} state={sta.state.value}")
    final, trace = associate_to_ap(sta, ap)
    for ev in trace:
        print(f"  {ev.frame:<24} {ev.src} -> {ev.dst:<20} [next: {ev.next_state.value}]")
    print(f"end:   STA {final.mac} state={final.state.value} bssid={final.associated_bssid.mac_str()}")


def demo_ess_routing() -> None:
    _hr("Demo 2: ESS routing across the Distribution System")
    ds = DistributionSystem(name="campus-ethernet")
    ap1 = AccessPoint(BSSID.from_ap_mac("aa:bb:cc:00:00:01"), "Campus", Channel(1, 2.4), "sw0/g1")
    ap2 = AccessPoint(BSSID.from_ap_mac("aa:bb:cc:00:00:02"), "Campus", Channel(6, 2.4), "sw0/g2")
    ds.register(ap1)
    ds.register(ap2)

    sta1, _ = associate_to_ap(Station(mac="00:11:22:33:44:55"), ap1)
    sta2, _ = associate_to_ap(Station(mac="00:11:22:33:44:66"), ap2)
    bss1 = BSS(ap=ap1, stations=(sta1,))
    bss2 = BSS(ap=ap2, stations=(sta2,))
    router = DsRouter(ds=ds, bsstable={ap1.bssid.mac_str(): bss1, ap2.bssid.mac_str(): bss2})

    print(f"STA1 {sta1.mac} is on {ap1.label()}")
    print(f"STA2 {sta2.mac} is on {ap2.label()}")
    for line in router.forward_inter_bss(sta1, sta2, "GET /index.html"):
        print(f"  {line}")
    print("DS log (frame crossings):")
    for src, dst, payload in ds.log:
        print(f"  {src} -> {dst}: {payload}")


def demo_ibss() -> None:
    _hr("Demo 3: IBSS ad hoc, no AP")
    rng = random.Random(42)
    ibss = make_random_ibss(rng, Channel(11, 2.4))
    a = Station(mac="de:ad:be:ef:00:01")
    b = Station(mac="de:ad:be:ef:00:02")
    c = Station(mac="de:ad:be:ef:00:03")
    ibss = ibss.with_member(a).with_member(b).with_member(c)
    print(f"IBSS bssid={ibss.bssid.mac_str()} channel={ibss.channel.label()} members={len(ibss.members)}")
    for line in ibss.forward_peer(a.mac, b.mac, "ping"):
        print(f"  {line}")
    for line in ibss.forward_peer(c.mac, a.mac, "ack"):
        print(f"  {line}")


def demo_reassociation_roaming() -> None:
    _hr("Demo 4: reassociation (roam) within an ESS")
    ap1 = AccessPoint(BSSID.from_ap_mac("aa:bb:cc:00:00:01"), "Campus", Channel(1, 2.4), "sw0/g1")
    ap2 = AccessPoint(BSSID.from_ap_mac("aa:bb:cc:00:00:02"), "Campus", Channel(6, 2.4), "sw0/g2")
    sta, _ = associate_to_ap(Station(mac="00:11:22:33:44:77"), ap1)
    print(f"start: STA {sta.mac} on {ap1.label()}")
    sta, trace = reassociate_to_ap(sta, ap1, ap2)
    for ev in trace:
        print(f"  {ev.frame:<24} {ev.src} -> {ev.dst:<20} [next: {ev.next_state.value}]")
    print(f"end:   STA {sta.mac} now on {ap2.label()}; IP layer unchanged.")


def demo_channel_reuse() -> None:
    _hr("Demo 5: 2.4 GHz channel-reuse plan (1/6/11)")
    plan = [(1, "AP1"), (6, "AP2"), (11, "AP3")]
    for n, name in plan:
        print(f"  {name} on {Channel(n, 2.4).label()}")
    pairs = [(plan[0], plan[1]), (plan[1], plan[2]), (plan[0], plan[2])]
    for (n1, _), (n2, _) in pairs:
        ov = channels_overlap(Channel(n1, 2.4), Channel(n2, 2.4))
        print(f"  channel {n1} vs channel {n2}: overlap={ov}  (good when False)")
    print("  channel 1 vs channel 3 (BAD plan):", channels_overlap(Channel(1, 2.4), Channel(3, 2.4)))


def demo_phy_table() -> None:
    _hr("Demo 6: 802.11 PHY evolution")
    print(f"  {'PHY':<12} {'year':<6} {'band':<10} {'modulation':<12} {'peak Mbps':>8}")
    for name, year, band, mod, peak in PHY_FLAVORS:
        print(f"  {name:<12} {year:<6} {band:<10} {mod:<12} {peak:>8}")


def main() -> None:
    demo_association_state_machine()
    demo_ess_routing()
    demo_ibss()
    demo_reassociation_roaming()
    demo_channel_reuse()
    demo_phy_table()
    print()
    print("All demos complete.")


if __name__ == "__main__":
    main()
