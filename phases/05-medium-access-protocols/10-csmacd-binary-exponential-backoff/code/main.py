"""CSMA/CD with Binary Exponential Backoff — IEEE 802.3 / 10BASE5 simulation.

A stdlib-only Python simulation of the classic Ethernet (10 Mbps) MAC
protocol described in Tanenbaum & Wetherall Computer Networks 5e §4.3.

Key mechanisms implemented:
* 1-persistent carrier sense: all stations fire immediately when channel is idle.
* Collision detection: any slot where >1 station fires is a collision.
* Binary exponential backoff (BEB): after the i-th collision (i ≤ 10), each
  station draws r uniformly from [0, 2^i − 1] and waits r × 51.2 µsec.
  Window frozen at [0, 1023] for collisions 11–15; frame dropped on the 16th.
* Ethernet frame builder: constructs the 8-field IEEE 802.3 frame with CRC-32.
* Channel efficiency: η = 1 / (1 + 2BLe/cF) from Metcalfe & Boggs (1976).
* Misbehaving NIC: one station that never backs off (always picks r=0).

Run:
    python3 code/main.py
"""

from __future__ import annotations

import random
import struct
import zlib
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# IEEE 802.3 / 10BASE5 physical constants
# ---------------------------------------------------------------------------

BIT_RATE_BPS: int = 10_000_000          # 10 Mbps
SLOT_BITS: int = 512                    # slot time in bits (= 2τ round-trip)
SLOT_US: float = SLOT_BITS / BIT_RATE_BPS * 1e6  # 51.2 µsec
PROPAGATION_SPEED: float = 2e8          # m/s in coax (≈ 0.67c)
MAX_SEGMENT_M: float = 2500.0           # 10BASE5 maximum segment length
IFG_BITS: int = 96                      # interframe gap (9.6 µsec at 10 Mbps)
JAM_BITS: int = 32                      # jam signal length
MIN_FRAME_BYTES: int = 64              # minimum Ethernet frame (data+header+FCS)
MAX_FRAME_BYTES: int = 1518            # maximum Ethernet frame
MAX_DATA_BYTES: int = 1500             # maximum payload
MIN_DATA_BYTES: int = 46               # minimum payload (before padding)
FCS_BYTES: int = 4
MAX_COLLISIONS: int = 16               # abort threshold
WINDOW_CAP_COLLISION: int = 10         # BEB window frozen after this many


# ---------------------------------------------------------------------------
# BEB core
# ---------------------------------------------------------------------------

def beb_contention_window(collision_count: int) -> int:
    """Return the upper bound (inclusive) of the BEB window after k collisions.

    Window = 2^min(k,10) − 1, so draw is from [0, window].
    """
    if collision_count <= 0:
        return 0
    k = min(collision_count, WINDOW_CAP_COLLISION)
    return (1 << k) - 1   # 2^k − 1


def beb_draw(collision_count: int, rng: random.Random, force_zero: bool = False) -> int:
    """Draw a random backoff from [0, 2^min(k,10) − 1].

    If force_zero is True (misbehaving NIC), always returns 0.
    """
    if force_zero:
        return 0
    window = beb_contention_window(collision_count)
    return rng.randint(0, window)


# ---------------------------------------------------------------------------
# Station state machine
# ---------------------------------------------------------------------------

_STATE_WAITING = "WAITING"    # Has a frame; will fire on next idle slot
_STATE_BACKOFF = "BACKOFF"    # Counting down random backoff slots
_STATE_DONE    = "DONE"       # Frame successfully delivered
_STATE_DROPPED = "DROPPED"    # Reached 16 collisions; frame abandoned


@dataclass
class Station:
    sid: int
    fair: bool = True            # False = misbehaving NIC (always r=0)

    state: str = _STATE_WAITING
    collision_count: int = 0     # consecutive collision counter
    backoff_remaining: int = 0   # slots left in current backoff period

    # --- per-frame statistics ---
    total_collisions: int = 0
    success_slot: int = -1       # slot at which the frame was delivered
    collision_history: list = field(default_factory=list)  # k value at each collision


# ---------------------------------------------------------------------------
# Ethernet frame builder (IEEE 802.3)
# ---------------------------------------------------------------------------

def _crc32_ethernet(data: bytes) -> int:
    """Compute Ethernet CRC-32 using zlib.crc32 (same polynomial 0x04C11DB7)."""
    return zlib.crc32(data) & 0xFFFFFFFF


@dataclass
class EthernetFrame:
    """Represent a fully encoded IEEE 802.3 frame.

    Fields (in wire order):
        preamble  8 bytes  (7 × 0xAA + 0xAB SFD)
        dst       6 bytes  destination MAC
        src       6 bytes  source MAC
        type_len  2 bytes  EtherType or Length
        data      46-1500 bytes  payload (padded if < 46 bytes)
        fcs       4 bytes  CRC-32 over dst+src+type_len+data
    """
    dst: bytes            # 6-byte destination MAC
    src: bytes            # 6-byte source MAC
    type_len: int         # 0x0800 = IPv4, 0x0806 = ARP, ≤0x0600 = length
    payload: bytes        # user payload (padded internally to ≥ 46 bytes)

    PREAMBLE: bytes = field(default=b'\xAA' * 7 + b'\xAB', init=False, repr=False)

    def _padded_payload(self) -> bytes:
        p = self.payload
        if len(p) < MIN_DATA_BYTES:
            p = p + b'\x00' * (MIN_DATA_BYTES - len(p))
        return p

    def encode(self) -> bytes:
        """Return the full on-wire byte string (including preamble)."""
        padded = self._padded_payload()
        header = self.dst + self.src + struct.pack('>H', self.type_len) + padded
        fcs = struct.pack('<I', _crc32_ethernet(header))
        return self.PREAMBLE + header + fcs

    def decode_report(self) -> str:
        """Human-readable field breakdown."""
        raw = self.encode()
        padded = self._padded_payload()
        header = self.dst + self.src + struct.pack('>H', self.type_len) + padded
        fcs_val = _crc32_ethernet(header)
        tl = self.type_len
        tl_desc = (
            f"EtherType=0x{tl:04X} (>0x0600, protocol frame)"
            if tl > 0x0600
            else f"Length={tl} (≤0x0600, IEEE 802.3)"
        )
        lines = [
            f"  Preamble+SFD : {self.PREAMBLE.hex().upper()!s:s}  ({len(self.PREAMBLE)} bytes)",
            f"  Dst MAC      : {':'.join(f'{b:02X}' for b in self.dst)}",
            f"  Src MAC      : {':'.join(f'{b:02X}' for b in self.src)}",
            f"  Type/Length  : 0x{tl:04X}  → {tl_desc}",
            f"  Data+Pad     : {len(padded)} bytes  (original payload {len(self.payload)} bytes)",
            f"  FCS (CRC-32) : 0x{fcs_val:08X}",
            f"  Total wire   : {len(raw)} bytes  "
            f"({'OK' if MIN_FRAME_BYTES <= len(raw) - len(self.PREAMBLE) + len(self.PREAMBLE) else 'RUNT'})",
        ]
        return '\n'.join(lines)


def build_frame_demo() -> None:
    """Print an annotated breakdown of a sample Ethernet frame."""
    print("=" * 65)
    print("IEEE 802.3 FRAME STRUCTURE DEMO")
    print("=" * 65)

    # IPv4 frame (EtherType = 0x0800)
    dst = bytes([0x00, 0x1A, 0x2B, 0x3C, 0x4D, 0x5E])
    src = bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])
    payload_ipv4 = b'Hello, Ethernet!' * 3          # 48 bytes → no padding needed
    frame = EthernetFrame(dst=dst, src=src, type_len=0x0800, payload=payload_ipv4)
    print("\n[1] IPv4 unicast frame (payload 48 bytes, no padding required)")
    print(frame.decode_report())

    # Short frame → padded to 46 bytes data
    short_payload = b'\xDE\xAD'                     # 2 bytes → pad to 46
    frame2 = EthernetFrame(dst=bytes(6), src=src, type_len=2, payload=short_payload)
    print("\n[2] Short payload (2 bytes → padded to 46, total frame = 64 bytes)")
    print(frame2.decode_report())

    # Broadcast ARP
    bcast = bytes([0xFF] * 6)
    frame3 = EthernetFrame(dst=bcast, src=src, type_len=0x0806, payload=b'\x00' * 28)
    print("\n[3] Broadcast ARP frame (EtherType 0x0806)")
    print(frame3.decode_report())

    print()


# ---------------------------------------------------------------------------
# Channel efficiency: η = 1 / (1 + 2BLe/cF)
# ---------------------------------------------------------------------------

def channel_efficiency(
    frame_bits: int,
    bandwidth_bps: float = BIT_RATE_BPS,
    cable_length_m: float = MAX_SEGMENT_M,
    prop_speed: float = PROPAGATION_SPEED,
) -> float:
    """Return CSMA/CD channel efficiency using Metcalfe & Boggs formula.

    η = 1 / (1 + 2BLe/cF)
    where B = bandwidth, L = cable length, e = 2.718…, c = prop speed,
    F = frame size in bits.
    """
    import math
    numerator = 2 * bandwidth_bps * cable_length_m * math.e
    denominator = prop_speed * frame_bits
    a = numerator / denominator
    return 1.0 / (1.0 + a)


def print_efficiency_table() -> None:
    """Print η for standard Ethernet frame sizes at 10 Mbps / 2500 m."""
    import math
    print("=" * 65)
    print("CHANNEL EFFICIENCY  η = 1 / (1 + 2BLe/cF)")
    print(f"B = {BIT_RATE_BPS/1e6:.0f} Mbps, L = {MAX_SEGMENT_M:.0f} m, "
          f"c = {PROPAGATION_SPEED:.0e} m/s, e = {math.e:.3f}")
    print("-" * 65)
    print(f"{'Frame (bytes)':>14} | {'Bits F':>7} | {'2BLe/cF':>9} | {'η':>7}")
    print("-" * 65)
    for frame_bytes in (64, 512, 1024, 1500):
        frame_bits = frame_bytes * 8
        eta = channel_efficiency(frame_bits)
        a = (2 * BIT_RATE_BPS * MAX_SEGMENT_M * 2.718281828) / (
            PROPAGATION_SPEED * frame_bits
        )
        print(f"{frame_bytes:>14} | {frame_bits:>7} | {a:>9.3f} | {eta:>6.1%}")
    print()


# ---------------------------------------------------------------------------
# CSMA/CD BEB simulator
# ---------------------------------------------------------------------------

@dataclass
class Simulator:
    """Slotted CSMA/CD shared-medium simulator.

    Time is measured in slots (1 slot = 51.2 µsec = 512 bit times).
    Stations use 1-persistent sensing: when the channel is idle they transmit
    immediately.  A frame transmission occupies
        ceil(frame_bytes * 8 / SLOT_BITS) slots.
    """

    stations: list[Station]
    rng: random.Random
    frame_bytes: int = 1518            # Ethernet max frame size (wire, no preamble)
    verbose: bool = False

    def frame_slots(self) -> int:
        """Number of slots required to transmit one frame (rounded up)."""
        return max(1, (self.frame_bytes * 8 + SLOT_BITS - 1) // SLOT_BITS)

    def run(self) -> int:
        """Simulate until all stations have succeeded or dropped their frame.

        Returns total number of slots consumed.
        """
        slot = 0
        frame_slots = self.frame_slots()
        channel_busy_until = 0   # slot at which the channel next becomes idle

        # Prepare: all stations start in WAITING state.
        for st in self.stations:
            st.state = _STATE_WAITING
            st.collision_count = 0
            st.backoff_remaining = 0
            st.total_collisions = 0
            st.success_slot = -1
            st.collision_history = []

        while any(st.state in (_STATE_WAITING, _STATE_BACKOFF)
                  for st in self.stations):
            # If channel is still busy from a previous transmission,
            # fast-forward to the slot where it clears.
            if slot < channel_busy_until:
                slot = channel_busy_until

            # Determine which stations fire this slot.
            # WAITING: fires immediately (1-persistent — channel idle → go).
            # BACKOFF: fires only if backoff_remaining reaches 0.
            firing: list[Station] = []
            for st in self.stations:
                if st.state == _STATE_WAITING:
                    firing.append(st)
                elif st.state == _STATE_BACKOFF:
                    if st.backoff_remaining == 0:
                        firing.append(st)

            if not firing:
                # Decrement backoff counters for stations in BACKOFF.
                for st in self.stations:
                    if st.state == _STATE_BACKOFF and st.backoff_remaining > 0:
                        st.backoff_remaining -= 1
                slot += 1
                continue

            if len(firing) == 1:
                # Single transmitter: success.
                winner = firing[0]
                winner.state = _STATE_DONE
                winner.success_slot = slot
                channel_busy_until = slot + frame_slots
                if self.verbose:
                    print(f"  slot {slot:>4}: Station {winner.sid} WINS "
                          f"(collisions={winner.total_collisions})")
                slot = channel_busy_until
                # Decrement counters for remaining BACKOFF stations (they
                # wait while channel is busy — counter frozen per 802.3).
            else:
                # Collision: all firing stations enter BEB.
                if self.verbose:
                    ids = [s.sid for s in firing]
                    print(f"  slot {slot:>4}: COLLISION  stations={ids}")
                for st in firing:
                    st.collision_count += 1
                    st.total_collisions += 1
                    st.collision_history.append(st.collision_count)
                    if st.collision_count >= MAX_COLLISIONS:
                        st.state = _STATE_DROPPED
                        if self.verbose:
                            print(f"           Station {st.sid} DROPPED "
                                  f"after {MAX_COLLISIONS} collisions")
                    else:
                        r = beb_draw(st.collision_count, self.rng,
                                     force_zero=not st.fair)
                        st.backoff_remaining = r
                        st.state = _STATE_BACKOFF
                        if self.verbose:
                            w = beb_contention_window(st.collision_count)
                            print(f"           Station {st.sid} backoff: "
                                  f"r={r}  window=[0,{w}]  "
                                  f"collision#{st.collision_count}")
                slot += 1

                # Decrement counters for other BACKOFF stations (not involved
                # in this collision — their counters keep running).
                for st in self.stations:
                    if st.state == _STATE_BACKOFF and st not in firing:
                        if st.backoff_remaining > 0:
                            st.backoff_remaining -= 1

        return slot


# ---------------------------------------------------------------------------
# Demo scenarios
# ---------------------------------------------------------------------------

def demo_beb_table() -> None:
    """Print the BEB contention window progression table."""
    print("=" * 65)
    print("BINARY EXPONENTIAL BACKOFF — CONTENTION WINDOW PROGRESSION")
    print("-" * 65)
    print(f"{'Collision k':>12} | {'Window [0, 2^k−1]':>18} | {'Max slots':>10} | {'Max wait (µs)':>14}")
    print("-" * 65)
    for k in range(1, 17):
        if k < MAX_COLLISIONS:
            w = beb_contention_window(k)
            wait_us = w * SLOT_US
            print(f"{k:>12} | {'[0, ' + str(w) + ']':>18} | {w:>10} | {wait_us:>14.1f}")
        else:
            print(f"{k:>12} | {'ABORT':>18} | {'—':>10} | {'—':>14}")
    print()


def demo_2_station(rng: random.Random) -> None:
    """Replicate the two-station worked example from the lesson prose."""
    print("=" * 65)
    print("TWO-STATION WORKED EXAMPLE (verbose trace)")
    print("-" * 65)
    stations = [Station(sid=0), Station(sid=1)]
    sim = Simulator(stations=stations, rng=rng, frame_bytes=64, verbose=True)
    total_slots = sim.run()
    print(f"  Total slots consumed: {total_slots}  ({total_slots * SLOT_US:.1f} µsec)")
    for st in stations:
        outcome = (f"DONE at slot {st.success_slot}"
                   if st.state == _STATE_DONE else "DROPPED")
        print(f"  Station {st.sid}: {outcome}  "
              f"collisions={st.total_collisions}  history={st.collision_history}")
    print()


def demo_collision_abort(rng: random.Random) -> None:
    """Force 16 consecutive collisions to demonstrate the abort path.

    We create two stations both configured as misbehaving NICs (always r=0)
    so they re-collide every slot until the abort threshold is reached.
    """
    print("=" * 65)
    print("ABORT SCENARIO — misbehaving NICs (r always = 0)")
    print("-" * 65)
    stations = [Station(sid=0, fair=False), Station(sid=1, fair=False)]
    sim = Simulator(stations=stations, rng=rng, frame_bytes=64, verbose=True)
    total_slots = sim.run()
    print(f"\n  Total slots consumed: {total_slots}")
    for st in stations:
        print(f"  Station {st.sid}: state={st.state}  "
              f"collisions={st.total_collisions}")
    print()


def demo_n_station_simulation(n: int, rng: random.Random,
                               frame_bytes: int = 1518) -> dict:
    """Simulate N fair stations contending for one frame each.

    Returns a summary dict.
    """
    stations = [Station(sid=i) for i in range(n)]
    sim = Simulator(stations=stations, rng=rng, frame_bytes=frame_bytes)
    total_slots = sim.run()

    done = [st for st in stations if st.state == _STATE_DONE]
    dropped = [st for st in stations if st.state == _STATE_DROPPED]
    collision_counts = [st.total_collisions for st in stations]
    success_slots = [st.success_slot for st in done]

    mean_collisions = sum(collision_counts) / len(collision_counts) if collision_counts else 0.0
    mean_success_slot = sum(success_slots) / len(success_slots) if success_slots else 0.0

    return {
        "n": n,
        "total_slots": total_slots,
        "done": len(done),
        "dropped": len(dropped),
        "mean_collisions": mean_collisions,
        "mean_success_slot": mean_success_slot,
        "max_collisions": max(collision_counts) if collision_counts else 0,
    }


def demo_sweep(rng: random.Random) -> None:
    """Sweep N from 2 to 32 and print mean collision rounds and slots-to-success."""
    print("=" * 65)
    print("N-STATION SWEEP — mean collision rounds and slots-to-success")
    print("(1518-byte frames, 10 Mbps, each station has one frame)")
    print("-" * 65)
    print(f"{'N':>4} | {'Done':>5} | {'Dropped':>7} | "
          f"{'Mean collisions':>15} | {'Max collisions':>14} | "
          f"{'Mean success slot':>18} | {'Total slots':>11}")
    print("-" * 65)
    for n in (2, 4, 8, 12, 16, 20, 24, 32):
        r = demo_n_station_simulation(n, random.Random(rng.randint(0, 2**31)))
        print(f"{r['n']:>4} | {r['done']:>5} | {r['dropped']:>7} | "
              f"{r['mean_collisions']:>15.2f} | {r['max_collisions']:>14} | "
              f"{r['mean_success_slot']:>18.1f} | {r['total_slots']:>11}")
    print()


def demo_fair_vs_unfair(rng: random.Random) -> None:
    """Compare one misbehaving NIC against N-1 fair stations."""
    print("=" * 65)
    print("FAIR vs MISBEHAVING NIC — starvation effect")
    print("(8 stations: station 0 is unfair; stations 1–7 are fair)")
    print("-" * 65)
    n = 8
    stations = [
        Station(sid=0, fair=False),          # misbehaving: always r=0
        *[Station(sid=i) for i in range(1, n)],
    ]
    sim = Simulator(stations=stations, rng=rng, frame_bytes=1518, verbose=False)
    total_slots = sim.run()

    print(f"  Total slots consumed: {total_slots}")
    print(f"  {'Station':>8} | {'Fair':>5} | {'State':>8} | "
          f"{'Collisions':>10} | {'Success slot':>12}")
    print(f"  {'-'*8} | {'-'*5} | {'-'*8} | {'-'*10} | {'-'*12}")
    for st in stations:
        outcome = (f"{st.success_slot:>12}"
                   if st.state == _STATE_DONE else f"{'DROPPED':>12}")
        print(f"  {st.sid:>8} | {str(st.fair):>5} | {st.state:>8} | "
              f"{st.total_collisions:>10} | {outcome}")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    rng = random.Random(42)

    # 1. BEB table: show the contention window at each collision step.
    demo_beb_table()

    # 2. Ethernet frame builder: show field breakdown.
    build_frame_demo()

    # 3. Channel efficiency table (Metcalfe & Boggs formula).
    print_efficiency_table()

    # 4. Two-station trace (matches the worked example in the lesson prose).
    demo_2_station(random.Random(7))

    # 5. Abort scenario: two misbehaving NICs → 16 collisions → drop.
    demo_collision_abort(random.Random(99))

    # 6. Sweep N from 2 to 32 showing collision degradation.
    demo_sweep(rng)

    # 7. Fair vs unfair NIC: starvation pattern.
    demo_fair_vs_unfair(random.Random(17))

    print("=" * 65)
    print("SUMMARY")
    print("-" * 65)
    print(f"  Slot time          : {SLOT_BITS} bits = {SLOT_US:.1f} µsec  (2τ at 10 Mbps)")
    print(f"  Min frame          : {MIN_FRAME_BYTES} bytes  (ensures frame spans ≥ 1 slot)")
    print(f"  Max collisions     : {MAX_COLLISIONS}  (abort threshold)")
    print(f"  Window cap         : after collision #{WINDOW_CAP_COLLISION}  "
          f"→ [0, {beb_contention_window(WINDOW_CAP_COLLISION)}] frozen")
    print(f"  η (64-byte frame)  : {channel_efficiency(512):.1%}  "
          f"(worst case — minimum frame on longest segment)")
    print(f"  η (1500-byte frame): {channel_efficiency(12000):.1%}  "
          f"(maximum Ethernet payload)")
    print()
    print("BEB keeps delay low at light load (small initial window) while")
    print("preventing livelock under heavy load (window grows exponentially,")
    print("spreading retransmissions over a wider range of slots).")
    print()
    print("Modern Ethernet bypasses CSMA/CD entirely: full-duplex switch ports")
    print("create point-to-point links where simultaneous TX/RX on separate")
    print("wire pairs makes electrical collisions impossible.")


if __name__ == "__main__":
    main()
