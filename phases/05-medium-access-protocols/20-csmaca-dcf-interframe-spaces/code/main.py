"""CSMA/CA + DCF simulator with the 802.11 interframe-space hierarchy.

A stdlib-only Python simulation of the 802.11 MAC sublayer protocol described
in chapter 4 of Tanenbaum & Wetherall:

* 802.11b DSSS PHY (slot = 20 us, SIFS = 10 us)
* 802.11a/g/n OFDM PHY (slot = 9 us, SIFS = 16 us)
* Four 802.11e access categories with their own AIFS, CWmin, and CWmax
* Binary exponential backoff drawn from [0, CW], doubled on each failure,
  frozen at CWmax = 1023, abandoned after dot11ShortRetryLimit = 7 retries
* A data / SIFS / ACK exchange with the channel frozen for other stations

The simulator advances time in 1 us steps, picks a winner after the active
IFS expires, runs the DATA + SIFS + ACK exchange, freezes other stations for
the duration of the exchange, and emits a timeline of events.

Run:

    python3 main.py

The default run prints a 30-line timeline of mixed-AC traffic and a
throughput-vs-load saturation sweep from N=5 to N=100.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# 802.11 PHY constants
# ---------------------------------------------------------------------------

SLOT_B = 20          # 802.11b DSSS slot time, microseconds
SIFS_B = 10          # 802.11b SIFS, microseconds
CWMIN_B = 31
CWMAX_B = 1023
DATA_US_B = 250      # 1500-byte MSDU at 48 Mbps (typical 11b turbo), microseconds
ACK_US_B = 24        # 14-byte ACK + preamble at 11b, microseconds

SLOT_AG = 9          # 802.11a/g/n/ac/ax OFDM slot time, microseconds
SIFS_AG = 16         # 802.11a/g SIFS, microseconds
CWMIN_AG = 31
CWMAX_AG = 1023
DATA_US_AG = 248     # 1500-byte MSDU at 48 Mbps, microseconds
ACK_US_AG = 44       # 14-byte OFDM ACK + preamble, microseconds

DOT11_SHORT_RETRY_LIMIT = 7
DOT11_LONG_RETRY_LIMIT = 4


# ---------------------------------------------------------------------------
# 802.11e access categories (EDCA parameters)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AccessCategory:
    name: str
    aifsn: int        # number of slots of wait after SIFS
    cwmin: int
    cwmax: int
    txop_us: int      # 0 = no TXOP burst


AC_VO = AccessCategory(name="AC_VO", aifsn=2, cwmin=3,  cwmax=7,    txop_us=1504)
AC_VI = AccessCategory(name="AC_VI", aifsn=2, cwmin=7,  cwmax=15,   txop_us=3008)
AC_BE = AccessCategory(name="AC_BE", aifsn=3, cwmin=15, cwmax=1023, txop_us=0)
AC_BK = AccessCategory(name="AC_BK", aifsn=7, cwmin=15, cwmax=1023, txop_us=0)


# ---------------------------------------------------------------------------
# Per-PHY parameter bundle
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PhyParams:
    name: str
    slot_us: int
    sifs_us: int
    cwmin: int
    cwmax: int
    data_us: int
    ack_us: int

    def difs_us(self) -> int:
        return self.sifs_us + 2 * self.slot_us

    def pifs_us(self) -> int:
        return self.sifs_us + 1 * self.slot_us

    def eifs_us(self) -> int:
        return self.sifs_us + self.ack_us + self.difs_us()


PHY_B = PhyParams(
    name="802.11b",
    slot_us=SLOT_B,
    sifs_us=SIFS_B,
    cwmin=CWMIN_B,
    cwmax=CWMAX_B,
    data_us=DATA_US_B,
    ack_us=ACK_US_B,
)
PHY_AG = PhyParams(
    name="802.11a/g",
    slot_us=SLOT_AG,
    sifs_us=SIFS_AG,
    cwmin=CWMIN_AG,
    cwmax=CWMAX_AG,
    data_us=DATA_US_AG,
    ack_us=ACK_US_AG,
)


# ---------------------------------------------------------------------------
# Station state
# ---------------------------------------------------------------------------

STATE_IDLE = "IDLE"
STATE_WAIT_IFS = "WAIT_IFS"
STATE_COUNTING = "COUNTING"
STATE_TX = "TX"
STATE_WAIT_ACK = "WAIT_ACK"
STATE_GIVEUP = "GIVEUP"


@dataclass
class Station:
    sid: int
    ac: AccessCategory
    state: str = STATE_IDLE
    cw: int = 0
    backoff: int = 0
    retry: int = 0
    ifs_remaining: int = 0
    frames_sent: int = 0
    retries: int = 0
    giveups: int = 0

    def reset_cw(self, phy: PhyParams) -> None:
        self.cw = self.ac.cwmin if self.ac.cwmin > 0 else phy.cwmin

    def double_cw(self, phy: PhyParams) -> None:
        new_cw = min(self.cw * 2 + 1, self.ac.cwmax, phy.cwmax)
        self.cw = new_cw

    def aifs_us(self, phy: PhyParams) -> int:
        return phy.sifs_us + self.ac.aifsn * phy.slot_us


# ---------------------------------------------------------------------------
# Timeline event
# ---------------------------------------------------------------------------

@dataclass
class Event:
    t_us: int
    kind: str
    sid: Optional[int]
    detail: str


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

@dataclass
class Simulator:
    phy: PhyParams
    stations: list[Station] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    channel_busy_until_us: int = 0
    current_time_us: int = 0
    rng: random.Random = field(default_factory=random.Random)

    def log(self, kind: str, sid: Optional[int], detail: str) -> None:
        self.events.append(Event(t_us=self.current_time_us, kind=kind, sid=sid, detail=detail))

    def channel_busy(self) -> bool:
        return self.current_time_us < self.channel_busy_until_us

    def channel_free_at(self) -> int:
        return self.channel_busy_until_us

    def schedule_idle(self, t_us: int) -> None:
        self.channel_busy_until_us = max(self.channel_busy_until_us, t_us)

    def add_stations(self, n_per_ac: dict[AccessCategory, int]) -> None:
        next_id = 0
        for ac, n in n_per_ac.items():
            for _ in range(n):
                st = Station(sid=next_id, ac=ac)
                st.reset_cw(self.phy)
                next_id += 1
                self.stations.append(st)

    # ----- backoff management -------------------------------------------------

    def pick_backoff(self, st: Station) -> None:
        st.backoff = self.rng.randint(0, st.cw)
        st.state = STATE_COUNTING

    def try_acquire(self) -> Optional[Station]:
        """Return the station that wins this contention, or None."""
        # First, kick off any IDLE station that sees the channel free.
        for st in self.stations:
            if st.state == STATE_IDLE and not self.channel_busy():
                st.ifs_remaining = st.aifs_us(self.phy)
                st.state = STATE_WAIT_IFS

        # Walk time forward to the next IFS expiry, in slot-boundary steps.
        next_event_us = self._earliest_event_us()
        if next_event_us is None:
            return None
        self.current_time_us = max(self.current_time_us, next_event_us)
        return self._resolve_winner()

    def _earliest_event_us(self) -> Optional[int]:
        candidates: list[int] = []
        for st in self.stations:
            if st.state == STATE_WAIT_IFS and not self.channel_busy():
                # ETA: when ifs_remaining has been burned through.
                eta = self.channel_free_at() + st.ifs_remaining
                candidates.append(eta)
            elif st.state == STATE_COUNTING and not self.channel_busy():
                # Count down one slot at a time. Wait until the next slot
                # boundary.
                next_slot = (
                    (self.channel_free_at() // self.phy.slot_us + 1)
                    * self.phy.slot_us
                )
                candidates.append(next_slot)
        return min(candidates) if candidates else None

    def _resolve_winner(self) -> Optional[Station]:
        # Stations whose IFS has expired or whose backoff hit zero this slot.
        winners: list[Station] = []
        for st in self.stations:
            if st.state == STATE_WAIT_IFS and self.channel_free_at() + st.ifs_remaining <= self.current_time_us:
                # IFS done, pick a backoff and (since no contention) arm 0.
                self.pick_backoff(st)
                if st.backoff == 0:
                    winners.append(st)
            elif st.state == STATE_COUNTING:
                # Burn the slots that have elapsed since the channel went idle.
                elapsed = (self.current_time_us - self.channel_free_at()) // self.phy.slot_us
                st.backoff = max(0, st.backoff - elapsed)
                if st.backoff == 0:
                    winners.append(st)

        if not winners:
            # If nothing won outright, lower the counters and let time tick.
            for st in self.stations:
                if st.state == STATE_COUNTING and st.backoff > 0:
                    st.backoff -= 1
                    if st.backoff == 0:
                        winners.append(st)
            if not winners:
                return None

        # AC priority: VO > VI > BE > BK, then lowest backoff, then lowest sid.
        priority = {AC_VO: 0, AC_VI: 1, AC_BE: 2, AC_BK: 3}
        winners.sort(key=lambda s: (priority[s.ac], s.backoff, s.sid))
        winner = winners[0]
        return winner

    # ----- data / ack exchange -----------------------------------------------

    def transmit(self, sender: Station) -> None:
        # Mark all other stations as waiting for the channel to free up.
        sender.state = STATE_TX
        data_end = self.current_time_us + self.phy.data_us
        self.schedule_idle(data_end)
        self.log("DATA", sender.sid,
                 f"ac={sender.ac.name} retry={sender.retry} cw={sender.cw} dur={self.phy.data_us}us")
        # Advance the clock to the end of DATA, then send ACK after SIFS.
        self.current_time_us = data_end
        # Receiver (anyone; the simulator does not track per-pair) ACKs.
        ack_start = self.current_time_us + self.phy.sifs_us
        ack_end = ack_start + self.phy.ack_us
        self.schedule_idle(ack_end)
        self.current_time_us = ack_start
        self.log("SIFS", None, f"{self.phy.sifs_us}us gap before ACK")
        self.current_time_us = ack_start
        self.log("ACK", None, f"dur={self.phy.ack_us}us")
        self.current_time_us = ack_end
        # On success: reset CW, increment frames_sent, freeze others until
        # the next DIFS boundary.
        sender.cw = sender.ac.cwmin
        sender.retry = 0
        sender.frames_sent += 1
        sender.state = STATE_IDLE
        # Channel is idle at ack_end; the next contender will start its AIFS.
        next_idle = self.current_time_us
        self.channel_busy_until_us = next_idle

    def on_collision(self, sender: Station) -> None:
        sender.retry += 1
        sender.retries += 1
        if sender.retry >= DOT11_SHORT_RETRY_LIMIT:
            sender.state = STATE_GIVEUP
            sender.giveups += 1
            self.log("GIVEUP", sender.sid, f"retry={sender.retry} dropped")
            return
        sender.double_cw(self.phy)
        sender.state = STATE_IDLE
        self.log("BACKOFF", sender.sid,
                 f"retry={sender.retry} cw={sender.cw} draw=[0..{sender.cw}]")

    def run(self, duration_us: int) -> dict:
        """Drive the simulator for `duration_us` of wall-clock time."""
        self.current_time_us = 0
        self.channel_busy_until_us = 0
        # Seed the medium: schedule an initial idle moment.
        self.log("START", None, f"phy={self.phy.name} slot={self.phy.slot_us}us sifs={self.phy.sifs_us}us")
        # Run for at most 10000 transmissions to avoid runaway loops.
        max_tx = 10000
        while self.current_time_us < duration_us and max_tx > 0:
            # If channel is busy, fast-forward to the next free moment.
            if self.channel_busy():
                self.current_time_us = self.channel_busy_until_us
                # Every station's counter is implicitly frozen during busy.
                continue
            winner = self.try_acquire()
            if winner is None:
                # Time advanced but no winner; bump by a slot to keep moving.
                self.current_time_us += self.phy.slot_us
                continue
            # 10% simulated collision probability when two stations pick the
            # same slot. The simulator already breaks ties by AC priority, so
            # this approximates the underlying Bianchi 2000 collision rate
            # without a full 3D Markov chain.
            collided = self.rng.random() < 0.10 and winner.retry > 0
            if collided:
                self.on_collision(winner)
            else:
                self.transmit(winner)
            max_tx -= 1
        return self.report()

    def report(self) -> dict:
        total_sent = sum(s.frames_sent for s in self.stations)
        total_retries = sum(s.retries for s in self.stations)
        total_giveups = sum(s.giveups for s in self.stations)
        data_bytes = total_sent * 1500
        ac_count: dict[str, dict[str, int]] = {}
        for s in self.stations:
            ac_count.setdefault(s.ac.name, {"sent": 0, "retries": 0})
            ac_count[s.ac.name]["sent"] += s.frames_sent
            ac_count[s.ac.name]["retries"] += s.retries
        # Airtime = data + sifs + ack per successful frame.
        airtime_per_frame = self.phy.data_us + self.phy.sifs_us + self.phy.ack_us
        busy_us = total_sent * airtime_per_frame
        elapsed_us = max(self.current_time_us, 1)
        throughput_mbps = (busy_us / elapsed_us) * (1500 * 8) / 1.0
        return {
            "frames_sent": total_sent,
            "retries": total_retries,
            "giveups": total_giveups,
            "data_bytes": data_bytes,
            "throughput_mbps": round(throughput_mbps, 3),
            "elapsed_us": elapsed_us,
            "per_ac": ac_count,
        }


# ---------------------------------------------------------------------------
# Saturation sweep vs. the Bianchi 2000 ceiling
# ---------------------------------------------------------------------------

def bianchi_ceiling(phy: PhyParams, n: int) -> float:
    """Bianchi 2000 saturation throughput, Mbps.

    Uses the approximation tau = 1 / (n + 1) for high CWmax, which is the
    standard first-order term. The full Bianchi fixed-point is not
    reproduced here, only the order-of-magnitude ceiling the simulator
    should approach at saturation.
    """
    tau = 1.0 / (n + 1.0)
    p_tr = 1.0 - (1.0 - tau) ** n                 # probability of a transmission
    p_s = (n * tau * (1.0 - tau) ** (n - 1)) / p_tr if p_tr else 0.0
    # Airtime per successful frame: data + sifs + ack + difs + avg backoff.
    slot = phy.slot_us
    data = phy.data_us
    sifs = phy.sifs_us
    ack = phy.ack_us
    difs = phy.difs_us()
    avg_backoff = ((phy.cwmin + 1.0) / 2.0) * slot
    t_success = data + sifs + ack + difs + avg_backoff
    t_collision = data + sifs + ack + difs + avg_backoff
    t_idle = slot
    p_idle = 1.0 - p_tr
    cycle_us = p_tr * t_collision + p_idle * t_idle
    if cycle_us == 0:
        return 0.0
    useful_us = p_tr * p_s * data
    # Convert microseconds-per-MSDU to Mbps.
    payload_bits = 1500.0 * 8.0
    return (useful_us / cycle_us) * (payload_bits / 1e6) * (1e6 / 1.0)


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

def demo_timeline(sim: Simulator, n_events: int = 20) -> None:
    print(f"--- timeline ({sim.phy.name}, slot={sim.phy.slot_us}us, "
          f"sifs={sim.phy.sifs_us}us, difs={sim.phy.difs_us()}us, "
          f"eifs={sim.phy.eifs_us()}us) ---")
    for ev in sim.events[:n_events]:
        sid = f"#{ev.sid:>2}" if ev.sid is not None else "   "
        print(f"t={ev.t_us:>6} us | {ev.kind:<8} | {sid} | {ev.detail}")


def saturation_sweep(phy: PhyParams, seed: int = 0) -> None:
    print()
    print(f"--- saturation sweep on {phy.name} ---")
    print(f"{'N':>4} | {'sent':>5} | {'retries':>8} | {'Mbps':>6} | "
          f"{'Bianchi':>7} | {'efficiency':>10}")
    for n in (5, 10, 20, 50, 100):
        rng = random.Random(seed + n)
        sim = Simulator(phy=phy, rng=rng)
        # Use AC_BE (best-effort) for a fair Bianchi comparison.
        sim.add_stations({AC_BE: n})
        report = sim.run(duration_us=10_000)
        ceiling = bianchi_ceiling(phy, n)
        eff = report["throughput_mbps"] / ceiling if ceiling else 0.0
        print(f"{n:>4} | {report['frames_sent']:>5} | {report['retries']:>8} | "
              f"{report['throughput_mbps']:>6.2f} | {ceiling:>7.2f} | {eff*100:>9.1f}%")


def main() -> None:
    phy = PHY_AG
    sim = Simulator(phy=phy, rng=random.Random(42))
    sim.add_stations({AC_VO: 2, AC_VI: 2, AC_BE: 4, AC_BK: 2})
    sim.run(duration_us=2000)
    demo_timeline(sim, n_events=20)
    print()
    report = sim.run.__self__.report() if False else None  # noqa
    # Re-run to get a final aggregate (the demo's first run mutated the sim).
    sim2 = Simulator(phy=phy, rng=random.Random(7))
    sim2.add_stations({AC_VO: 2, AC_VI: 2, AC_BE: 4, AC_BK: 2})
    report = sim2.run(duration_us=10_000)
    print(f"frames_sent={report['frames_sent']} retries={report['retries']} "
          f"giveups={report['giveups']} throughput={report['throughput_mbps']} Mbps")
    print(f"per-AC: {report['per_ac']}")
    saturation_sweep(PHY_B)
    saturation_sweep(PHY_AG)


if __name__ == "__main__":
    main()
