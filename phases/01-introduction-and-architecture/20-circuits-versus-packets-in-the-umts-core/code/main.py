"""
UMTS core-network simulator: circuit-switched voice admission control vs
packet-switched best-effort queueing, plus soft/hard handover frame handling.

Models the textbook (Tanenbaum & Wetherall, Sec. 1.5.2) split of the UMTS
3G core behind one RNC: voice calls cross Iu-CS to the MSC, which reserves a
64 kbps PCM timeslot on a fixed-capacity trunk or rejects with a busy signal;
data sessions cross Iu-PS to the SGSN/GGSN over a GTP tunnel (UDP/2152) and
share a best-effort queue on the Gn link that drops packets under overload.

Stdlib only. Run:  python3 main.py
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Tunable network parameters
# ---------------------------------------------------------------------------
TRUNK_SLOTS = 8          # PCM timeslots MSC<->PSTN (8 x 64 kbps voice calls)
VOICE_BPS = 64_000       # uncompressed PCM voice rate per call
GN_RATE = 2_000_000      # SGSN<->GGSN Gn link capacity (bits/s)
GN_BUFFER_BYTES = 1_000_000  # finite Gn queue (about 0.5 s at link rate)
PKT_SIZE = 1500          # bytes per IP packet on the PS path
TICK_MS = 100            # discrete-time step for the PS simulation
HANDOVER_FRAME_MS = 20   # one voice frame per tick (AMR-like)

GTP_U_PORT = 2152        # 3GPP TS 29.060 GTP-U user-plane UDP port


# ---------------------------------------------------------------------------
# Circuit-switched path: a counting-semaphore trunk
# ---------------------------------------------------------------------------
@dataclass
class CircuitTrunk:
    """A fixed pool of reserved-or-rejected voice slots (the MSC view)."""

    slots: int
    _free: int = field(init=False)
    _calls: dict[int, float] = field(default_factory=dict)  # call_id -> end_time

    def __post_init__(self) -> None:
        self._free = self.slots

    def admit(self, call_id: int, now: float, duration: float) -> bool:
        """Try to reserve one slot for `duration` seconds. Reject if full."""
        if self._free <= 0:
            return False
        self._free -= 1
        self._calls[call_id] = now + duration
        return True

    def release(self, call_id: int) -> None:
        if call_id in self._calls:
            self._free += 1
            del self._calls[call_id]

    def tick(self, now: float) -> list[int]:
        """Release every call whose holding time has expired at `now`."""
        expired = [cid for cid, end in self._calls.items() if end <= now]
        for cid in expired:
            self.release(cid)
        return expired

    @property
    def free(self) -> int:
        return self._free


def simulate_circuit_core(
    n_calls: int, trunk_slots: int, mean_hold: float, window: float, seed: int = 7
) -> tuple[list[tuple[int, str]], int]:
    """Admit a burst of voice calls; report accept/reject per call."""
    random.seed(seed)
    trunk = CircuitTrunk(slots=trunk_slots)
    log: list[tuple[int, str]] = []
    admitted = 0
    # All calls arrive essentially together (the Friday 17:55 burst).
    for cid in range(n_calls):
        ok = trunk.admit(cid, now=0.0, duration=random.expovariate(1.0 / mean_hold))
        if ok:
            log.append((cid, "ACCEPTED (slot reserved)"))
            admitted += 1
        else:
            log.append((cid, "REJECTED (busy signal - trunk full)"))
    # Drain the trunk over the window so the demo shows clean release.
    t = 0.0
    while trunk._calls and t < window:  # noqa: SLF001
        t += 1.0
        trunk.tick(t)
    return log, admitted


# ---------------------------------------------------------------------------
# Packet-switched path: a finite best-effort queue on the Gn link
# ---------------------------------------------------------------------------
@dataclass
class PacketQueue:
    """Drop-tail FIFO queue served at a fixed packet rate per tick."""

    rate_per_tick: int          # packets the link can drain each tick
    capacity: int               # max packets buffered
    _buf: list[int] = field(default_factory=list)
    offered: int = 0
    dropped: int = 0
    served: int = 0

    def enqueue(self, n: int) -> None:
        for _ in range(n):
            self.offered += 1
            if len(self._buf) >= self.capacity:
                self.dropped += 1
            else:
                self._buf.append(self.offered)

    def drain(self) -> int:
        n = min(self.rate_per_tick, len(self._buf))
        del self._buf[:n]
        self.served += n
        return n

    @property
    def occupancy(self) -> int:
        return len(self._buf)


def simulate_packet_core(
    offered_ratio: float,
    gn_rate_bps: int = GN_RATE,
    buffer_bytes: int = GN_BUFFER_BYTES,
    pkt_size: int = PKT_SIZE,
    tick_ms: int = TICK_MS,
    ticks: int = 500,
    seed: int = 11,
) -> dict[str, float]:
    """Run a discrete-time PS load test at `offered_ratio` of Gn capacity."""
    random.seed(seed)
    pkts_per_tick_capacity = gn_rate_bps // (pkt_size * 8) * tick_ms // 1000
    pkts_per_tick_capacity = max(1, pkts_per_tick_capacity)
    buffer_pkts = max(1, buffer_bytes // pkt_size)
    q = PacketQueue(rate_per_tick=pkts_per_tick_capacity, capacity=buffer_pkts)

    mean_arrival = int(round(pkts_per_tick_capacity * offered_ratio))
    for _ in range(ticks):
        # Bursty on/off source: Gaussian arrivals around the offered mean.
        arrivals = int(random.gauss(mean_arrival, max(1.0, mean_arrival * 0.4)))
        if arrivals < 0:
            arrivals = 0
        q.enqueue(arrivals)
        q.drain()

    loss_rate = q.dropped / q.offered if q.offered else 0.0
    return {
        "offered": q.offered,
        "served": q.served,
        "dropped": q.dropped,
        "loss_rate": loss_rate,
        "final_occupancy": q.occupancy,
        "capacity_pkts_per_tick": pkts_per_tick_capacity,
        "buffer_pkts": buffer_pkts,
    }


# ---------------------------------------------------------------------------
# GTP-U tunnel: a forwarding label, not a reservation
# ---------------------------------------------------------------------------
@dataclass
class GTPTunnel:
    """A GTP-U tunnel (TEID on UDP/2152). Carries no bandwidth guarantee."""

    teid: int
    sgsn_addr: str
    ggsn_addr: str
    mobile_ip: str
    reserved_bps: int = 0  # a pure label reserves nothing by default

    def encapsulate(self, inner_src: str, inner_dst: str, payload: bytes) -> bytes:
        header = (
            f"GTP-U teid={self.teid:#010x} port={GTP_U_PORT} "
            f"{self.sgsn_addr}->{self.ggsn_addr}"
        ).encode()
        return header + b"|" + payload

    @property
    def is_circuit(self) -> bool:
        return self.reserved_bps > 0


# ---------------------------------------------------------------------------
# Handover: soft (make-before-break) vs hard (break-before-make)
# ---------------------------------------------------------------------------
def soft_handover(overlap_frames: int) -> dict[str, int]:
    """Mobile held by two Node Bs during overlap; RNC combines frames."""
    delivered = 0
    for _ in range(overlap_frames):
        # Both links up -> one combined frame delivered, zero lost.
        delivered += 1
    return {"frames_delivered": delivered, "frames_lost": 0, "gap_ms": 0}


def hard_handover(overlap_frames: int, gap_frames: int) -> dict[str, int]:
    """Old link torn down before new one is up; frames in the gap are lost."""
    delivered = overlap_frames - gap_frames
    lost = gap_frames
    return {
        "frames_delivered": max(0, delivered),
        "frames_lost": lost,
        "gap_ms": lost * HANDOVER_FRAME_MS,
    }


# ---------------------------------------------------------------------------
# HSS lookup: how either core finds the mobile
# ---------------------------------------------------------------------------
@dataclass
class HSS:
    """Home Subscriber Server: IMSI -> current serving node."""

    subscribers: dict[str, dict[str, str]] = field(default_factory=dict)

    def register(self, imsi: str, serving: str, location_area: str) -> None:
        self.subscribers[imsi] = {
            "serving_node": serving,
            "location_area": location_area,
        }

    def route_request(self, imsi: str) -> str:
        entry = self.subscribers.get(imsi)
        if entry is None:
            raise KeyError(f"unknown IMSI {imsi}")
        return entry["serving_node"]


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 72)
    print("UMTS CORE: CIRCUIT (Iu-CS) vs PACKET (Iu-PS)")
    print("=" * 72)

    # --- Circuit path: admission control on an 8-slot trunk ---
    print("\n[1] Circuit path - MSC admission control on a "
          f"{TRUNK_SLOTS}-slot PCM trunk")
    n_calls = 10
    log, admitted = simulate_circuit_core(
        n_calls=n_calls, trunk_slots=TRUNK_SLOTS, mean_hold=120.0, window=300.0
    )
    for cid, status in log:
        print(f"    call {cid:2d}: {status}")
    rejected = n_calls - admitted
    print(f"    -> admitted={admitted}, rejected={rejected} (busy signal) "
          f"of {n_calls} requested")
    print(f"    -> each admitted call holds a {VOICE_BPS} bps slot for its "
          "whole duration; admitted calls suffer NO degradation")

    # --- Packet path: loss under overload ---
    print("\n[2] Packet path - Gn best-effort queue "
          f"(capacity {GN_RATE/1e6:.0f} Mbps, buffer {GN_BUFFER_BYTES/1e6:.1f} MB)")
    print(f"    {'load':>6} {'offered':>8} {'served':>8} "
          f"{'dropped':>8} {'loss%':>7} {'occup':>6}")
    for ratio in (0.5, 0.9, 1.0, 1.5, 2.0, 3.0):
        r = simulate_packet_core(offered_ratio=ratio)
        print(f"    {ratio:>6.1f} {r['offered']:>8} {r['served']:>8} "
              f"{r['dropped']:>8} {r['loss_rate']*100:>6.2f}% "
              f"{r['final_occupancy']:>6}")
    print("    -> below saturation loss ~0; above saturation loss climbs "
          "toward (offered-capacity)/offered")

    # --- GTP tunnel: a label, not a circuit ---
    print("\n[3] GTP-U tunnel - a 32-bit TEID on UDP/2152, no reservation")
    tun = GTPTunnel(teid=0x12345678, sgsn_addr="10.1.2.3",
                    ggsn_addr="10.9.8.7", mobile_ip="100.64.0.5")
    enc = tun.encapsulate("203.0.113.9", "100.64.0.5", b"<1500B IP packet>")
    print(f"    {enc.decode()}")
    print(f"    is_circuit={tun.is_circuit}  "
          f"(reserved_bps={tun.reserved_bps}) -> a label, not a timeslot")

    # --- Handover ---
    print("\n[4] Handover frame accounting (20 ms voice frames)")
    overlap = 10  # 200 ms overlap window
    s = soft_handover(overlap)
    h = hard_handover(overlap, gap_frames=3)  # 60 ms break-make gap
    print(f"    soft (make-before-break): {s}")
    print(f"    hard (break-before-make): {h}")

    # --- HSS routing ---
    print("\n[5] HSS lookup - IMSI -> serving node (queried via MAP)")
    hss = HSS()
    hss.register("234150000001234", serving="MSC-3", location_area="LA-0xB1")
    hss.register("234150000009991", serving="SGSN-7", location_area="LA-0xC2")
    for imsi in ("234150000001234", "234150000009991"):
        print(f"    IMSI {imsi} -> serving {hss.route_request(imsi)}")

    print("\n[6] Verdict")
    print("    circuit core: deterministic QoS, rejects on exhaustion, "
          "aborts on path failure")
    print("    packet core:  best-effort, degrades under load, reroutes "
          "around failure")
    print("    => LTE collapses both into one all-IP core (3GPP TS 23.401).")


if __name__ == "__main__":
    main()
