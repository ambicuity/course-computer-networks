"""IEEE 802.11 (Wi-Fi) DCF toolkit — frame decode, backoff math, contention sim.

Stdlib-only, no network calls. Three independent pieces tied to the lesson:

1. parse_frame_control: decode the 16-bit 802.11 Frame Control field
   (Type/Subtype, ToDS/FromDS, Retry, Protected, ...).
2. backoff_window / max_backoff_us: binary exponential backoff — the
   contention window doubles 15 -> 31 -> ... -> 1023 on each missed ACK.
3. simulate_dcf: a slotted discrete-event Distributed Coordination Function
   simulation that demonstrates throughput collapse under hidden terminals.

Run:  python3 main.py
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List

# --- DCF timing constants (802.11a/g/n OFDM PHY, microseconds) ---------------
SLOT_US = 9          # SlotTime
SIFS_US = 16         # Short interframe space (ACK/CTS priority)
DIFS_US = SIFS_US + 2 * SLOT_US   # = 34 us, normal data access
CW_MIN = 15          # contention window floor
CW_MAX = 1023        # contention window ceiling

# --- Frame Control bit layout (Type/Subtype values we care about) ------------
FRAME_TYPES = {0: "management", 1: "control", 2: "data", 3: "extension"}
CONTROL_SUBTYPES = {0xB: "RTS", 0xC: "CTS", 0xD: "ACK"}
MGMT_SUBTYPES = {0x0: "AssocRequest", 0x4: "ProbeRequest", 0x8: "Beacon"}


@dataclass
class FrameControl:
    """Decoded 802.11 Frame Control field."""

    version: int
    ftype: int
    subtype: int
    to_ds: bool
    from_ds: bool
    more_frag: bool
    retry: bool
    protected: bool

    def label(self) -> str:
        kind = FRAME_TYPES.get(self.ftype, "?")
        if self.ftype == 1:
            kind = f"control/{CONTROL_SUBTYPES.get(self.subtype, hex(self.subtype))}"
        elif self.ftype == 0:
            kind = f"mgmt/{MGMT_SUBTYPES.get(self.subtype, hex(self.subtype))}"
        elif self.ftype == 2:
            kind = "data"
        return kind

    def address_count(self) -> int:
        """A 4th address appears only on a WDS link (ToDS and FromDS both set)."""
        return 4 if (self.to_ds and self.from_ds) else 3


def build_frame_control(
    ftype: int,
    subtype: int,
    *,
    to_ds: bool = False,
    from_ds: bool = False,
    retry: bool = False,
    protected: bool = False,
    version: int = 0,
) -> int:
    """Pack fields into a 16-bit Frame Control word: octet0 = [subtype|type|ver],
    octet1 = flags. Inverse of parse_frame_control."""
    octet0 = (version & 0b11) | ((ftype & 0b11) << 2) | ((subtype & 0b1111) << 4)
    flags = (
        (0x01 if to_ds else 0)
        | (0x02 if from_ds else 0)
        | (0x08 if retry else 0)
        | (0x40 if protected else 0)
    )
    return octet0 | (flags << 8)


def parse_frame_control(fc: int) -> FrameControl:
    """Decode the 16-bit Frame Control word. Octet0 holds Version/Type/Subtype,
    octet1 holds the flag bits (ToDS, FromDS, Retry, ...)."""
    if not 0 <= fc <= 0xFFFF:
        raise ValueError(f"Frame Control must be 16 bits, got {fc:#x}")
    version = fc & 0b11
    ftype = (fc >> 2) & 0b11
    subtype = (fc >> 4) & 0b1111
    flags = (fc >> 8) & 0xFF
    return FrameControl(
        version=version,
        ftype=ftype,
        subtype=subtype,
        to_ds=bool(flags & 0x01),
        from_ds=bool(flags & 0x02),
        more_frag=bool(flags & 0x04),
        retry=bool(flags & 0x08),
        protected=bool(flags & 0x40),
    )


def backoff_window(attempt: int) -> int:
    """Contention window CW for the Nth transmission attempt (1-indexed)."""
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    cw = (CW_MIN + 1) * (2 ** (attempt - 1)) - 1
    return min(cw, CW_MAX)


def max_backoff_us(attempt: int) -> int:
    """Worst-case backoff time (us) before the Nth attempt: CW slots * SlotTime."""
    return backoff_window(attempt) * SLOT_US


@dataclass
class Station:
    name: str
    cw: int = CW_MIN
    backoff: int = 0
    attempt: int = 1
    delivered: int = 0
    collisions: int = 0
    backoff_total: int = 0

    def arm(self, rng: random.Random) -> None:
        """Draw a fresh backoff counter uniformly from [0, CW]."""
        self.backoff = rng.randint(0, self.cw)
        self.backoff_total += self.backoff

    def on_success(self, rng: random.Random) -> None:
        self.delivered += 1
        self.cw = CW_MIN
        self.attempt = 1
        self.arm(rng)

    def on_collision(self, rng: random.Random) -> None:
        self.collisions += 1
        self.attempt += 1
        self.cw = backoff_window(self.attempt)
        self.arm(rng)


def simulate_dcf(
    n_stations: int,
    rounds: int,
    hidden: bool = False,
    seed: int = 7,
) -> Dict[str, object]:
    """DCF backoff model contrasting an audible cell with hidden terminals.

    Each transmission attempt is one round. Every contending station has armed a
    backoff counter from [0, CW].

    - Audible cell: carrier sense works. The station(s) with the *smallest*
      backoff transmit; everyone else hears the medium go busy and freezes.
      A collision happens only when two or more stations tie for the minimum
      backoff (they picked the same slot and fired together).

    - Hidden terminals: stations cannot hear each other, so carrier sense fails.
      Every station that reaches a transmit opportunity in the contention period
      blasts the AP; whenever more than one does so in the window they collide,
      which is dramatically more often than the tie-only audible case.
    """
    rng = random.Random(seed)
    stations: List[Station] = [Station(f"STA{i}") for i in range(n_stations)]
    for s in stations:
        s.arm(rng)

    # Hidden stations cannot freeze their counters on a busy medium (they never
    # sense it busy), so two counters can expire close together. We model a
    # short vulnerable window: any other hidden station whose backoff lands
    # within HIDDEN_WINDOW slots of the firing station also transmits -> collide.
    hidden_window = 1

    for _ in range(rounds):
        lowest = min(s.backoff for s in stations)
        if hidden:
            firing = [s for s in stations if s.backoff <= lowest + hidden_window]
        else:
            firing = [s for s in stations if s.backoff == lowest]

        # Advance virtual time: everyone counts down to the firing point.
        for s in stations:
            s.backoff = max(0, s.backoff - lowest)

        if len(firing) == 1:
            firing[0].on_success(rng)
        else:
            for s in firing:
                s.on_collision(rng)

    delivered = sum(s.delivered for s in stations)
    collisions = sum(s.collisions for s in stations)
    avg_backoff = sum(s.backoff_total for s in stations) / max(1, delivered + collisions)
    return {
        "delivered": delivered,
        "collisions": collisions,
        "efficiency": delivered / max(1, delivered + collisions),
        "avg_backoff_slots": round(avg_backoff, 2),
        "stations": stations,
    }


def _hr() -> None:
    print("-" * 64)


def main() -> None:
    print("802.11 DCF TOOLKIT\n")

    # 1) Frame Control decode -------------------------------------------------
    print("Frame Control decode")
    _hr()
    samples = [
        (build_frame_control(2, 0, to_ds=True), "data, ToDS (client -> AP)"),
        (build_frame_control(2, 0, from_ds=True, retry=True),
         "data, FromDS + Retry (AP -> client, retransmit)"),
        (build_frame_control(1, 0xB), "control/RTS"),
        (build_frame_control(1, 0xC), "control/CTS"),
        (build_frame_control(2, 0, to_ds=True, from_ds=True),
         "data, ToDS+FromDS (WDS bridge, 4 addresses)"),
        (build_frame_control(0, 0x8), "mgmt/Beacon"),
    ]
    for raw, note in samples:
        fc = parse_frame_control(raw)
        print(
            f"  {raw:#06x}  {fc.label():<18} addrs={fc.address_count()} "
            f"ToDS={int(fc.to_ds)} FromDS={int(fc.from_ds)} "
            f"Retry={int(fc.retry)}  [{note}]"
        )

    # 2) Binary exponential backoff ------------------------------------------
    print("\nBinary exponential backoff (OFDM 9 us slots)")
    _hr()
    print("  attempt   CW   max backoff")
    for attempt in range(1, 8):
        print(
            f"     {attempt}     {backoff_window(attempt):>4}   "
            f"{max_backoff_us(attempt):>5} us"
        )

    # 3) DCF contention simulation -------------------------------------------
    print("\nDCF contention simulation (8 stations, 4000 slots)")
    _hr()
    for hidden in (False, True):
        res = simulate_dcf(n_stations=8, rounds=4000, hidden=hidden)
        tag = "HIDDEN TERMINALS" if hidden else "all stations audible"
        print(
            f"  {tag:<20} delivered={res['delivered']:>4}  "
            f"collisions={res['collisions']:>4}  "
            f"efficiency={res['efficiency']:.1%}  "
            f"avg_backoff={res['avg_backoff_slots']} slots"
        )
    print(
        "\n  Note: hidden terminals collide at the AP with no local carrier\n"
        "  sense, so collisions rise and efficiency drops -- the conference-\n"
        "  room symptom. RTS/CTS publishes a NAV so hidden nodes defer."
    )


if __name__ == "__main__":
    main()
