"""Fast Ethernet PHY reference: 4B/5B encoding, MLT-3 signaling, and 802.3u auto-negotiation.

Implements the four core mechanisms from the Fast Ethernet PHY lesson:

  1. 4B/5B block coding — maps each 4-bit nibble to a 5-bit code group.
     Overhead: 100 Mbps data requires a 125 Mbaud code-group stream (5/4 ratio).
  2. MLT-3 line signaling — three-level voltage cycling (-1/0/+1/0) on copper.
     Only encoded-1 bits advance the state; 0 bits hold the current voltage.
  3. 802.3u auto-negotiation — Fast Link Pulse (FLP) bursts carry a 16-bit
     Link Code Word advertising speed/duplex capabilities; priority resolution
     selects the highest common mode.
  4. Duplex mismatch — forcing one side to 100/full while leaving the other on
     auto produces asymmetric errors that look like application-layer failures.

Stdlib only.  No pip dependencies.

Usage:
    python3 code/main.py                          Run all demonstrations.
    python3 code/main.py encode <hex>             4B/5B encode nibbles (e.g. 0xA3).
    python3 code/main.py mlt3 <bitstring>         MLT-3 transitions on an encoded bit string.
    python3 code/main.py autoneg <caps_A> <caps_B>
                                                  Resolve negotiation between two devices.
                                                  Caps: comma-separated from
                                                  {100TX-FD,100TX-HD,10T-FD,10T-HD}.
    python3 code/main.py mismatch                 Simulate forced/auto duplex mismatch.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Final

# ---------------------------------------------------------------------------
# 4B/5B encoding table  (IEEE 802.3u / FDDI)
# ---------------------------------------------------------------------------

# Maps 4-bit nibble index (0–15) to 5-bit code group.
# Every code group guarantees at least two 1-bits, so the receiver can always
# recover the clock.  The 25 % expansion is: 5 bits out / 4 bits in.
FOUR_B_FIVE_B: Final[tuple[int, ...]] = (
    0b11110,  # 0x0 -> 30
    0b01001,  # 0x1 ->  9
    0b10100,  # 0x2 -> 20
    0b10101,  # 0x3 -> 21
    0b01010,  # 0x4 -> 10
    0b01011,  # 0x5 -> 11
    0b01110,  # 0x6 -> 14
    0b01111,  # 0x7 -> 15
    0b10010,  # 0x8 -> 18
    0b10011,  # 0x9 -> 19
    0b10110,  # 0xA -> 22
    0b10111,  # 0xB -> 23
    0b11010,  # 0xC -> 26
    0b11011,  # 0xD -> 27
    0b11100,  # 0xE -> 28
    0b11101,  # 0xF -> 29
)

# Control symbols (not data).  Sent during idle and frame delimiters.
SYM_IDLE: Final[int] = 0b11111  # 31 - inter-frame idle
SYM_J:    Final[int] = 0b11000  # 24 - Start-of-Stream Delimiter part 1
SYM_K:    Final[int] = 0b10001  # 17 - Start-of-Stream Delimiter part 2
SYM_T:    Final[int] = 0b01101  # 13 - End-of-Stream Delimiter part 1
SYM_R:    Final[int] = 0b00111  #  7 - End-of-Stream Delimiter part 2

# Reverse lookup: 5-bit code -> human label.
_REVERSE: Final[dict[int, str]] = {v: f"D[{i:X}]" for i, v in enumerate(FOUR_B_FIVE_B)}
_REVERSE.update({
    SYM_IDLE: "IDLE",
    SYM_J:    "J",
    SYM_K:    "K",
    SYM_T:    "T",
    SYM_R:    "R",
})


def _nibbles_from_hex(hex_str: str) -> list[int]:
    """Parse a hex string into a list of 4-bit nibbles, most-significant first."""
    clean = hex_str.strip().lower().removeprefix("0x")
    if not clean:
        raise ValueError("empty hex string")
    return [int(c, 16) for c in clean]


def encode_nibbles(nibbles: list[int]) -> list[int]:
    """Return the 5-bit code groups for a list of 4-bit nibbles."""
    return [FOUR_B_FIVE_B[n] for n in nibbles]


def code_group_bits(code: int) -> list[int]:
    """Expand a 5-bit code group into a list of 5 bits, most-significant first."""
    return [(code >> (4 - i)) & 1 for i in range(5)]


def encode_frame_bytes(data: bytes) -> list[int]:
    """Encode a byte sequence as a framed 4B/5B symbol stream.

    Adds J+K Start-of-Stream Delimiter, encodes every nibble, then appends
    T+R End-of-Stream Delimiter.  The stream preceding the frame and trailing
    it would carry continuous IDLE symbols on a live link.
    """
    symbols: list[int] = [SYM_J, SYM_K]
    for byte in data:
        high = (byte >> 4) & 0xF
        low  =  byte       & 0xF
        symbols.append(FOUR_B_FIVE_B[high])
        symbols.append(FOUR_B_FIVE_B[low])
    symbols.extend([SYM_T, SYM_R])
    return symbols


# ---------------------------------------------------------------------------
# MLT-3 line signaling
# ---------------------------------------------------------------------------

# The three-level sequence.  The index advances on each encoded-1 bit.
MLT3_CYCLE: Final[tuple[int, ...]] = (-1, 0, +1, 0)


@dataclass
class MLT3State:
    """Stateful MLT-3 encoder: converts an encoded bit stream to voltage levels."""
    _idx: int = 0

    def feed(self, bit: int) -> int:
        """Feed one encoded bit; return the resulting line voltage (-1, 0, or +1)."""
        if bit == 1:
            self._idx = (self._idx + 1) % 4
        return MLT3_CYCLE[self._idx]

    def feed_all(self, bits: list[int]) -> list[int]:
        return [self.feed(b) for b in bits]

    @property
    def current_level(self) -> int:
        return MLT3_CYCLE[self._idx]


def count_transitions(levels: list[int]) -> int:
    """Count voltage transitions in an MLT-3 level sequence."""
    if len(levels) < 2:
        return 0
    return sum(1 for a, b in zip(levels, levels[1:]) if a != b)


def max_transition_frequency_hz(baud_rate: float = 125_000_000.0) -> float:
    """Return the maximum transition frequency (Hz) for MLT-3 at the given baud rate.

    For 100Base-TX at 125 Mbaud, the worst case is alternating 1s in the
    encoded stream, which advances the MLT-3 cycle once per symbol.  The
    cycle length is 4, so the maximum transition frequency is baud/4.
    """
    return baud_rate / 4.0


# ---------------------------------------------------------------------------
# Auto-negotiation  (IEEE 802.3, clause 28)
# ---------------------------------------------------------------------------

# Capability names understood by this module.
VALID_CAPS: Final[frozenset[str]] = frozenset({"100TX-FD", "100TX-HD", "10T-FD", "10T-HD"})

# Priority order: highest to lowest.  The first common capability wins.
AUTONEG_PRIORITY: Final[tuple[str, ...]] = (
    "100TX-FD",  # 100Base-TX full duplex  — most preferred
    "100TX-HD",  # 100Base-TX half duplex
    "10T-FD",    # 10Base-T full duplex
    "10T-HD",    # 10Base-T half duplex    — least preferred
)

# Human labels for reporting.
_CAP_LABEL: Final[dict[str, str]] = {
    "100TX-FD": "100Base-TX full duplex",
    "100TX-HD": "100Base-TX half duplex",
    "10T-FD":   "10Base-T full duplex",
    "10T-HD":   "10Base-T half duplex",
}

# Approximate bit-positions in the 16-bit Link Code Word (base page).
# Bits 5-9 are the technology ability field; bit 14 is Acknowledge.
LCW_BITS: Final[dict[str, int]] = {
    "10T-HD":   5,
    "10T-FD":   6,
    "100TX-HD": 7,
    "100TX-FD": 8,
}


def build_lcw(caps: set[str], acknowledge: bool = False) -> int:
    """Build a 16-bit Link Code Word for the given capability set.

    The selector field (bits 0-4) is set to 00001 (IEEE 802.3).
    """
    lcw = 0b00001  # selector = 802.3
    for cap, bit in LCW_BITS.items():
        if cap in caps:
            lcw |= 1 << bit
    if acknowledge:
        lcw |= 1 << 14
    return lcw


def parse_lcw(lcw: int) -> set[str]:
    """Return the capability set advertised in a Link Code Word."""
    return {cap for cap, bit in LCW_BITS.items() if lcw & (1 << bit)}


def autoneg_resolve(caps_a: set[str], caps_b: set[str]) -> str | None:
    """Return the highest common capability, or None if there is no overlap."""
    common = caps_a & caps_b
    for mode in AUTONEG_PRIORITY:
        if mode in common:
            return mode
    return None


# ---------------------------------------------------------------------------
# Duplex mismatch simulation
# ---------------------------------------------------------------------------

@dataclass
class LinkEndpoint:
    """Represents one end of an Ethernet link for negotiation purposes."""
    name: str
    forced: bool          # True if speed/duplex is administratively forced
    forced_mode: str      # e.g. "100TX-FD" when forced=True
    advertised: set[str]  # capabilities advertised via FLP when not forced

    def effective_mode(self) -> str:
        """Return the mode this endpoint ends up with after negotiation."""
        return self.forced_mode if self.forced else ""


def simulate_link(a: LinkEndpoint, b: LinkEndpoint) -> dict[str, str]:
    """Simulate link-up between two endpoints.

    Returns a dict with keys "mode_a", "mode_b", "mismatch", and "consequence".
    """
    if not a.forced and not b.forced:
        # Both sides run full auto-negotiation.
        selected = autoneg_resolve(a.advertised, b.advertised)
        if selected is None:
            return {
                "mode_a":      "link-down",
                "mode_b":      "link-down",
                "mismatch":    "no common capability",
                "consequence": "Link stays down; check advertised modes on both sides.",
            }
        return {
            "mode_a":      selected,
            "mode_b":      selected,
            "mismatch":    "none",
            "consequence": "Clean link.  Both sides operate at the same speed and duplex.",
        }

    if a.forced and b.forced:
        # Both sides forced; if modes differ, the link may still come up but
        # at mismatched settings.
        if a.forced_mode == b.forced_mode:
            return {
                "mode_a":      a.forced_mode,
                "mode_b":      b.forced_mode,
                "mismatch":    "none (forced identical)",
                "consequence": "Clean link.  Both sides forced to the same mode.",
            }
        # Speeds must still match for a link to form.
        speed_a = a.forced_mode.split("-")[0]
        speed_b = b.forced_mode.split("-")[0]
        if speed_a != speed_b:
            return {
                "mode_a":      a.forced_mode,
                "mode_b":      b.forced_mode,
                "mismatch":    "speed mismatch",
                "consequence": "Link stays down.  Incompatible baud rates on wire.",
            }
        return {
            "mode_a":      a.forced_mode,
            "mode_b":      b.forced_mode,
            "mismatch":    "duplex mismatch (forced vs forced)",
            "consequence": (
                "Link is up but asymmetric.  "
                "Full-duplex side sees FCS/align errors.  "
                "Half-duplex side sees late collisions and drops."
            ),
        }

    # One side forced, one side auto: the classic duplex mismatch.
    forced_ep  = a if a.forced else b
    auto_ep    = b if a.forced else a
    forced_mode = forced_ep.forced_mode

    # The auto side can infer speed from the signal rate but cannot read duplex
    # from an endpoint that suppresses FLPs.  It falls back to half duplex.
    forced_speed = forced_mode.split("-")[0]   # e.g. "100TX"
    auto_inferred = forced_speed + "-HD"        # always half duplex without FLP

    if forced_ep is a:
        mode_a, mode_b = forced_mode, auto_inferred
    else:
        mode_a, mode_b = auto_inferred, forced_mode

    is_mismatch = ("FD" in forced_mode and "HD" in auto_inferred) or \
                  ("HD" in forced_mode and "FD" in auto_inferred)

    consequence = (
        "Duplex mismatch!  "
        f"{forced_ep.name} operates {forced_mode} (forced).  "
        f"{auto_ep.name} auto-detects speed but falls back to HD → {auto_inferred}.  "
        "The full-duplex side transmits without listening for collisions.  "
        "The half-duplex side detects late collisions.  "
        "Counter signature: FCS/align errors ↑ on FD side, late-collisions ↑ on HD side."
    ) if is_mismatch else (
        "Modes happen to match despite forced/auto asymmetry.  "
        "Forcing both sides to the same mode would be more reliable."
    )

    return {
        "mode_a":      mode_a,
        "mode_b":      mode_b,
        "mismatch":    "duplex mismatch" if is_mismatch else "none (accidental match)",
        "consequence": consequence,
    }


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def _hr(char: str = "-", width: int = 68) -> None:
    print(char * width)


def cmd_encode(hex_str: str) -> int:
    """4B/5B encode nibbles from a hex string and show overhead arithmetic."""
    try:
        nibbles = _nibbles_from_hex(hex_str)
    except (ValueError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    codes = encode_nibbles(nibbles)
    input_bits  = len(nibbles) * 4
    output_bits = len(nibbles) * 5
    overhead_pct = (output_bits / input_bits - 1) * 100

    print(f"\n{'4B/5B Encoding':^68}")
    _hr()
    print(f"Input hex    : {hex_str}")
    print(f"Nibbles      : {' '.join(f'{n:X}' for n in nibbles)}   ({len(nibbles)} nibbles, {input_bits} bits)")
    print(f"Symbol rate  : 100 Mbps × 5/4 = 125 Mbaud  (overhead {overhead_pct:.0f}%)")
    _hr()
    print(f"  {'Nibble':>6}  {'Code (5-bit)':>12}  {'Name':>6}  {'One-bits':>8}  {'Transitions':>11}")
    _hr()
    for nibble, code in zip(nibbles, codes):
        bits_str  = format(code, "05b")
        name      = _REVERSE.get(code, "?")
        ones      = bits_str.count("1")
        bits_list = [(code >> (4 - i)) & 1 for i in range(5)]
        tr        = sum(1 for x, y in zip(bits_list, bits_list[1:]) if x != y)
        print(f"  {nibble:6X}  {bits_str:>12}  {name:>6}  {ones:>8}  {tr:>11}")
    _hr()
    print(f"Input:  {input_bits} bits  -> Output: {output_bits} code bits  (ratio 5:4, {overhead_pct:.0f}% overhead)")

    # Verify no code group has fewer than 2 ones (clock-recovery guarantee).
    min_ones = min(format(c, "05b").count("1") for c in codes)
    print(f"Min 1-bits per code group: {min_ones}  (>= 2 guarantees clock recovery)")
    print()
    return 0


def cmd_mlt3(bit_string: str) -> int:
    """Show MLT-3 transitions for a binary bit string."""
    if not all(c in "01" for c in bit_string):
        print("Error: bit string must contain only '0' and '1'.", file=sys.stderr)
        return 2

    bits = [int(c) for c in bit_string]
    encoder = MLT3State()
    levels = encoder.feed_all(bits)
    transitions = count_transitions(levels)
    max_freq = max_transition_frequency_hz(125_000_000.0)

    print(f"\n{'MLT-3 Signaling':^68}")
    _hr()
    print(f"Encoded bit stream : {bit_string}  ({len(bits)} bits)")
    print(f"Baud rate          : 125 Mbaud  (after 4B/5B)")
    print(f"Max transition freq: {max_freq / 1e6:.0f} MHz  (baud/4, worst case alternating 1s)")
    _hr()
    print(f"  {'Bit':>3}  {'Level':>6}  {'Transition':>10}")
    _hr()
    prev = None
    for i, (bit, level) in enumerate(zip(bits, levels)):
        tr_str = "<-- transition" if prev is not None and level != prev else ""
        print(f"  {bit:>3}  {level:>+6}  {tr_str}")
        prev = level
    _hr()
    print(f"Total transitions: {transitions} / {len(bits)} bits "
          f"  ({100 * transitions / max(len(bits), 1):.0f}%  vs 100% for binary signaling)")

    # Compare to NRZ binary: every 1 bit would cause a transition.
    nrz_transitions = sum(bits)
    print(f"Binary NRZ equiv : {nrz_transitions} transitions  "
          f"(MLT-3 reduces frequency by distributing transitions across 4-step cycle)")
    print()
    return 0


def cmd_autoneg(caps_str_a: str, name_a: str, caps_str_b: str, name_b: str) -> int:
    """Resolve auto-negotiation between two devices and show the LCW exchange."""
    def parse_caps(s: str) -> set[str] | None:
        caps: set[str] = set()
        for token in s.split(","):
            t = token.strip().upper()
            if t not in VALID_CAPS:
                print(f"Error: unknown capability '{t}'.  Valid: {sorted(VALID_CAPS)}",
                      file=sys.stderr)
                return None
            caps.add(t)
        return caps

    caps_a = parse_caps(caps_str_a)
    caps_b = parse_caps(caps_str_b)
    if caps_a is None or caps_b is None:
        return 2

    lcw_a = build_lcw(caps_a)
    lcw_b = build_lcw(caps_b)
    # After receiving peer LCW, each side sends ACK.
    lcw_a_ack = build_lcw(caps_a, acknowledge=True)
    lcw_b_ack = build_lcw(caps_b, acknowledge=True)

    selected = autoneg_resolve(caps_a, caps_b)
    common   = caps_a & caps_b

    print(f"\n{'Auto-negotiation (Fast Link Pulse exchange)':^68}")
    _hr()
    print(f"Device {name_a} advertises : {', '.join(sorted(caps_a))}")
    print(f"  LCW: 0x{lcw_a:04X}  ({lcw_a:016b})")
    print()
    print(f"Device {name_b} advertises : {', '.join(sorted(caps_b))}")
    print(f"  LCW: 0x{lcw_b:04X}  ({lcw_b:016b})")
    _hr()
    print(f"Common capabilities: {', '.join(sorted(common)) if common else 'none'}")
    _hr()
    print(f"Priority walk (highest first):")
    for mode in AUTONEG_PRIORITY:
        in_a = mode in caps_a
        in_b = mode in caps_b
        in_common = mode in common
        marker = " <-- SELECTED" if mode == selected else ""
        print(f"  {_CAP_LABEL[mode]:<30}  "
              f"A={'yes' if in_a else 'no ':3}  B={'yes' if in_b else 'no ':3}  "
              f"common={'yes' if in_common else 'no'}{marker}")
    _hr()
    if selected:
        print(f"Negotiated mode: {_CAP_LABEL[selected]}")
        print(f"  ACK from {name_a}: 0x{lcw_a_ack:04X}")
        print(f"  ACK from {name_b}: 0x{lcw_b_ack:04X}")
    else:
        print("Result: NO common capability.  Link stays down.")
    print()
    return 0


def cmd_mismatch() -> int:
    """Simulate the forced 100/full vs auto duplex mismatch scenario."""
    print(f"\n{'Duplex Mismatch Scenario':^68}")
    _hr()

    # Define the two endpoints.
    server_nic = LinkEndpoint(
        name="Server NIC",
        forced=True,
        forced_mode="100TX-FD",
        advertised=set(),  # FLPs suppressed when forced
    )
    switch_port = LinkEndpoint(
        name="Switch port",
        forced=False,
        forced_mode="",
        advertised={"100TX-FD", "100TX-HD", "10T-FD", "10T-HD"},
    )

    print(f"{'Endpoint':<16}  {'Forced?':>7}  {'Config':>14}  {'FLP sent?':>9}")
    _hr("-")
    print(f"{'Server NIC':<16}  {'yes':>7}  {'100/full':>14}  {'no':>9}  (FLPs suppressed)")
    print(f"{'Switch port':<16}  {'no':>7}  {'auto':>14}  {'yes':>9}  (advertises all modes)")
    _hr()

    result = simulate_link(server_nic, switch_port)

    print(f"\nLink-up outcome:")
    print(f"  Server NIC  : {result['mode_a']}")
    print(f"  Switch port : {result['mode_b']}")
    print(f"  Mismatch    : {result['mismatch']}")
    _hr()
    print(f"Consequence:")
    print(f"  {result['consequence']}")
    _hr()

    # Show the counter signature operators would see.
    print("\nExpected counter pattern (after 60 seconds of traffic load):")
    print("  Server NIC (100FD, forced):")
    print("    rx_fcs_errors      ↑↑   — gets frames collided by switch's HD retransmits")
    print("    rx_align_errors    ↑    — fragment bursts from switch HD collisions")
    print("    tx_collisions      0    — FD side never backs off")
    print("  Switch port (100HD, auto-inferred):")
    print("    late_collisions    ↑↑   — switch transmits while NIC is also sending (FD)")
    print("    tx_collisions      ↑↑   — HD side keeps backing off (exponential backoff)")
    print("    throughput         ↓↓   — effective bandwidth collapses under load")
    _hr()
    print("\nFix: either force BOTH sides to 100/full, or enable auto on BOTH sides.")
    print()
    return 0


def cmd_demo() -> int:
    """Run all four demonstrations in sequence."""
    print("=" * 68)
    print("  Fast Ethernet PHY — 4B/5B, MLT-3, Auto-Negotiation Demo")
    print("=" * 68)

    # 1. 4B/5B encoding of two realistic nibble sequences.
    print("\n[1/4]  4B/5B Encoding — nibbles from 0xDE (a typical MAC byte)")
    rc = cmd_encode("0xDE")
    if rc:
        return rc

    print("\n[1b/4] 4B/5B Encoding — all-zeros nibble (potential clock starvation without coding)")
    rc = cmd_encode("0x00")
    if rc:
        return rc

    # 2. MLT-3 on representative bit patterns.
    print("\n[2/4]  MLT-3 — all-zeros encoded stream (no transitions)")
    rc = cmd_mlt3("00000")
    if rc:
        return rc

    print("\n[2b/4] MLT-3 — alternating 1s (maximum transition rate, shows baud/4 reduction)")
    rc = cmd_mlt3("10101010")
    if rc:
        return rc

    print("\n[2c/4] MLT-3 — realistic frame-like encoded sequence (mixed 0s and 1s)")
    # J+K SSD for 100Base-TX: 11000 10001
    rc = cmd_mlt3("1100010001")
    if rc:
        return rc

    # 3. Auto-negotiation matrix (five representative device pairs).
    print("\n[3/4]  Auto-Negotiation — five device-pair cases")
    _hr("=")
    cases = [
        ("100TX-FD,100TX-HD,10T-FD,10T-HD", "A",
         "100TX-FD,100TX-HD,10T-FD,10T-HD", "B",
         "Both full capability — should select 100TX-FD"),
        ("10T-HD,10T-FD,100TX-HD",           "A",
         "10T-FD,100TX-FD",                  "B",
         "A advertises 100TX half but not full; B has 100TX-FD only — best common is 10T-FD"),
        ("100TX-FD,100TX-HD",                "A",
         "100TX-FD,100TX-HD",                "B",
         "Both 100TX only — should select 100TX-FD"),
        ("10T-HD",                           "A",
         "100TX-FD,100TX-HD,10T-FD,10T-HD",  "B",
         "A is 10/HD only — should fall to 10T-HD"),
        ("10T-FD",                           "A",
         "100TX-FD,100TX-HD",                "B",
         "No common mode — link stays down"),
    ]
    for i, (ca, na, cb, nb, desc) in enumerate(cases, 1):
        print(f"\n  Case {i}: {desc}")
        _hr("-")
        rc = cmd_autoneg(ca, na, cb, nb)
        if rc:
            return rc

    # 4. Duplex mismatch.
    print("\n[4/4]  Duplex Mismatch — forced 100/full NIC vs auto switch port")
    rc = cmd_mismatch()
    if rc:
        return rc

    # Summary table.
    print("=" * 68)
    print("  Summary")
    print("=" * 68)
    rows = [
        ("4B/5B overhead",    "4 data bits -> 5 code bits",   "100 Mbps needs 125 Mbaud"),
        ("MLT-3 max freq",    "baud_rate / 4",                "31.25 MHz vs 125 MHz binary"),
        ("100Base-TX",        "Cat5 copper, 2 pairs",         "4B/5B + MLT-3"),
        ("100Base-FX",        "Multimode fiber, 2 fibers",    "4B/5B + NRZI"),
        ("100Base-T4",        "Cat3 copper, 4 pairs",         "8B/6T ternary"),
        ("Autoneg winner",    "Priority resolution",          "100TX-FD > 100TX-HD > 10T-FD > 10T-HD"),
        ("Duplex mismatch",   "Forced FD + auto HD",          "FCS errors ↑ + late collisions ↑"),
    ]
    print(f"  {'Concept':<22}  {'Mechanism':<30}  {'Key number/result'}")
    _hr()
    for concept, mechanism, result in rows:
        print(f"  {concept:<22}  {mechanism:<30}  {result}")
    _hr()
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv

    if not args or args[0] in ("demo", "--demo"):
        return cmd_demo()

    cmd = args[0].lower()

    if cmd == "encode":
        if len(args) < 2:
            print("Usage: encode <hex>  e.g. encode 0xA3", file=sys.stderr)
            return 2
        return cmd_encode(args[1])

    if cmd == "mlt3":
        if len(args) < 2:
            print("Usage: mlt3 <bitstring>  e.g. mlt3 10110100", file=sys.stderr)
            return 2
        return cmd_mlt3(args[1])

    if cmd == "autoneg":
        if len(args) < 5:
            print(
                "Usage: autoneg <caps_A> <name_A> <caps_B> <name_B>\n"
                "  caps: comma-separated from {100TX-FD,100TX-HD,10T-FD,10T-HD}\n"
                "  e.g.: autoneg 100TX-FD,10T-FD A 100TX-FD,100TX-HD B",
                file=sys.stderr,
            )
            return 2
        return cmd_autoneg(args[1], args[2], args[3], args[4])

    if cmd == "mismatch":
        return cmd_mismatch()

    print(f"Unknown command: {cmd}", file=sys.stderr)
    print("Available commands: encode, mlt3, autoneg, mismatch, demo", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
