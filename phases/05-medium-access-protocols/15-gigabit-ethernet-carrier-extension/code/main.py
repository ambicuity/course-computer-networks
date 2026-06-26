"""Gigabit Ethernet Carrier Extension, Frame Bursting, and 8B/10B Coding.

Implements IEEE 802.3z (1998) half-duplex mechanisms:
  - Slot-time analysis at 10 / 100 / 1000 Mbps vs. cable length
  - Carrier extension efficiency (frame sizes 46–1500 bytes)
  - Frame burst efficiency for queue depths 1–50 (64-byte frames)
  - Encoding overhead comparison: Manchester, 4B/5B, 8B/10B, 64B/66B
  - 8B/10B running-disparity demonstration
  - PAUSE frame structure and timing at 1 Gbps

Run:
    python3 code/main.py
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

SPEED_OF_LIGHT_MPS: float = 3.0e8     # m/s in vacuum
SLOT_BITS: int = 512                   # bit-times — identical at all speeds
EXTENSION_BYTE: int = 0x0F            # 8B/10B K-code used as fill symbol
MAC_OVERHEAD_BYTES: int = 18          # DA(6) + SA(6) + EtherType(2) + FCS(4)
PREAMBLE_BYTES: int = 8               # 7 × 0xAA + SFD 0xAB
MIN_PAYLOAD_BYTES: int = 46           # minimum MAC payload before software pad
MIN_FRAME_BYTES: int = 64             # minimum MAC frame (header + padded data + FCS)
IFE_BYTES: int = 12                   # inter-frame extension fill per gap in burst
IFG_BITS: int = 96                    # normal interframe gap in bit-times
BURST_CAP_BYTES: int = 65_536         # maximum burst length (IEEE 802.3z §4.2.3)
CE_MIN_WIRE_BYTES: int = 512          # carrier extension target (4096 bits)


# ---------------------------------------------------------------------------
# 1. Slot-time analysis
# ---------------------------------------------------------------------------

@dataclass
class SlotTimeResult:
    speed_bps: float
    distance_m: float
    vf: float
    prop_speed_mps: float
    round_trip_ns: float
    slot_time_ns: float
    csmacd_ok: bool


def slot_time_check(speed_bps: float, distance_m: float, vf: float) -> SlotTimeResult:
    """Compute round-trip propagation time and compare it to the 512-bit slot time.

    Parameters
    ----------
    speed_bps   : link rate in bits per second (e.g. 1e9 for 1 Gbps)
    distance_m  : one-way cable length in metres
    vf          : velocity factor of the medium (0.59 for Cat5 UTP)

    Returns
    -------
    SlotTimeResult with round_trip_ns, slot_time_ns, and csmacd_ok flag.
    """
    prop_speed = vf * SPEED_OF_LIGHT_MPS
    round_trip_ns = (2.0 * distance_m / prop_speed) * 1e9
    slot_time_ns = (SLOT_BITS / speed_bps) * 1e9
    return SlotTimeResult(
        speed_bps=speed_bps,
        distance_m=distance_m,
        vf=vf,
        prop_speed_mps=prop_speed,
        round_trip_ns=round_trip_ns,
        slot_time_ns=slot_time_ns,
        csmacd_ok=(round_trip_ns <= slot_time_ns),
    )


def print_slot_time_table() -> None:
    """Print slot-time analysis for 10 / 100 / 1000 Mbps at key distances."""
    print("=" * 76)
    print("SLOT-TIME ANALYSIS — Does CSMA/CD guarantee collision detection?")
    print("Slot time = 512 bit-times / link_rate  |  v_f = 0.59 (Cat5 UTP)")
    print("-" * 76)
    hdr = f"{'Speed':>10} | {'Distance':>10} | {'Slot time':>12} | {'Round-trip':>12} | {'Result'}"
    sub = f"{'(Mbps)':>10} | {'(m)':>10} | {'(ns)':>12} | {'(ns)':>12} |"
    print(hdr)
    print(sub)
    print("-" * 76)

    scenarios: list[tuple[float, float, float]] = [
        (10e6,   2500, 0.59),   # 10BASE5 maximum segment
        (10e6,    500, 0.59),   # 10BASE5 practical run
        (100e6,   200, 0.59),   # 100BASE-TX maximum segment
        (100e6,   100, 0.59),   # 100BASE-TX typical run
        (1000e6,   25, 0.59),   # 1000Base-T — practical half-duplex limit
        (1000e6,   45, 0.59),   # 1000Base-T — cable-only theoretical limit
        (1000e6,   80, 0.59),   # 1000Base-T — 80 m building wiring (FAILS)
        (1000e6,  200, 0.59),   # 1000Base-T + carrier extension — 200 m ok
    ]

    for speed, dist, vf in scenarios:
        r = slot_time_check(speed, dist, vf)
        mbps = speed / 1e6
        status = "OK" if r.csmacd_ok else "FAILS (CE needed)"
        print(
            f"{mbps:>10.0f} | {dist:>10.0f} | "
            f"{r.slot_time_ns:>12.1f} | {r.round_trip_ns:>12.1f} | {status}"
        )

    print()
    print("  At 1 Gbps, slot time = 512 ns.  Cable-only propagation at 45 m ≈ 508 ns")
    print("  (just within spec); repeater/transceiver delays cut practical limit to ~25 m.")
    print("  Carrier extension stretches the slot to 4096 ns → ~200 m practical range.")
    print()


# ---------------------------------------------------------------------------
# 2. Carrier extension efficiency
# ---------------------------------------------------------------------------

@dataclass
class CEResult:
    payload_bytes: int
    frame_bytes: int           # MAC frame (DA+SA+Type+Data+FCS), no preamble
    wire_bytes: int            # on-wire bytes after carrier extension if required
    extension_bytes: int       # 0x0F fill appended (0 when frame >= 512 bytes)
    line_efficiency: float     # frame_bytes / wire_bytes
    payload_efficiency: float  # payload_bytes / wire_bytes


def carrier_extension_efficiency(payload_bytes: int) -> CEResult:
    """Return carrier extension overhead for a given payload size.

    The MAC layer pads payloads shorter than 46 bytes to reach the 64-byte
    minimum frame.  If the resulting frame is shorter than 512 bytes the NIC
    hardware appends 0x0F fill to bring the on-wire total to exactly 512 bytes.
    Frames >= 512 bytes need no extension.
    """
    effective_payload = max(payload_bytes, MIN_PAYLOAD_BYTES)
    frame_bytes = effective_payload + MAC_OVERHEAD_BYTES   # e.g. 46 + 18 = 64
    wire_bytes = max(frame_bytes, CE_MIN_WIRE_BYTES)
    extension_bytes = wire_bytes - frame_bytes
    return CEResult(
        payload_bytes=payload_bytes,
        frame_bytes=frame_bytes,
        wire_bytes=wire_bytes,
        extension_bytes=extension_bytes,
        line_efficiency=frame_bytes / wire_bytes,
        payload_efficiency=payload_bytes / wire_bytes,
    )


def print_ce_efficiency_table() -> None:
    """Print carrier extension overhead for representative payload sizes."""
    print("=" * 76)
    print("CARRIER EXTENSION EFFICIENCY")
    print("Extension symbol = 0x0F (8B/10B K-code, stripped by receiver NIC)")
    print("-" * 76)
    print(
        f"{'Payload':>10} | {'Frame':>8} | {'Wire':>8} | "
        f"{'CE fill':>8} | {'Line eff.':>10} | {'Payload eff.':>12} | Note"
    )
    print(
        f"{'(bytes)':>10} | {'(bytes)':>8} | {'(bytes)':>8} | "
        f"{'(bytes)':>8} | {'':>10} | {'':>12} |"
    )
    print("-" * 76)

    payloads = [46, 100, 200, 300, 400, 494, 500, 1000, 1500]
    for p in payloads:
        r = carrier_extension_efficiency(p)
        note = "no CE" if r.extension_bytes == 0 else ""
        print(
            f"{r.payload_bytes:>10} | {r.frame_bytes:>8} | "
            f"{r.wire_bytes:>8} | {r.extension_bytes:>8} | "
            f"{r.line_efficiency:>9.1%} | {r.payload_efficiency:>11.1%} | {note}"
        )

    print()
    r46 = carrier_extension_efficiency(46)
    print(
        f"  Worst case: {r46.payload_bytes}-byte payload in {r46.wire_bytes}-byte on-wire slot "
        f"= {r46.payload_efficiency:.0%} payload efficiency"
    )
    print("  At 1 Gbps: only ~90 Mbps of actual user data delivered with min-size frames.")
    print("  Frame bursting (below) recovers much of this loss for queued senders.")
    print()


# ---------------------------------------------------------------------------
# 3. Frame bursting
# ---------------------------------------------------------------------------

@dataclass
class BurstResult:
    frame_count: int
    frame_bytes: int
    payload_per_frame: int
    frames_in_burst: int
    total_payload_bytes: int
    wire_bytes: int
    burst_efficiency: float
    ce_solo_efficiency: float
    burst_cap_exceeded: bool


def frame_burst_efficiency(frame_count: int, frame_bytes: int) -> BurstResult:
    """Return burst efficiency for N identical frames.

    Structure: [CE-padded frame 1][IFE 12 B][frame 2][IFE 12 B]...[frame N]
    First frame uses carrier extension (padded to 512 bytes if shorter).
    Subsequent frames are transmitted at normal size preceded by 12-byte IFE fill.
    Total burst capped at BURST_CAP_BYTES (65,536) per IEEE 802.3z §4.2.3.
    """
    eff_frame = max(frame_bytes, MIN_FRAME_BYTES)
    payload_per = eff_frame - MAC_OVERHEAD_BYTES

    first_wire = max(eff_frame, CE_MIN_WIRE_BYTES)   # CE padding on frame 1
    per_subsequent = eff_frame + IFE_BYTES            # IFE fill + frame bytes

    frames_in_burst = 1
    running = first_wire
    cap_exceeded = False
    for _ in range(1, frame_count):
        candidate = running + per_subsequent
        if candidate > BURST_CAP_BYTES:
            cap_exceeded = True
            break
        running = candidate
        frames_in_burst += 1

    total_payload = frames_in_burst * payload_per
    ce_solo = carrier_extension_efficiency(payload_per)

    return BurstResult(
        frame_count=frame_count,
        frame_bytes=eff_frame,
        payload_per_frame=payload_per,
        frames_in_burst=frames_in_burst,
        total_payload_bytes=total_payload,
        wire_bytes=running,
        burst_efficiency=total_payload / running,
        ce_solo_efficiency=ce_solo.payload_efficiency,
        burst_cap_exceeded=cap_exceeded,
    )


def print_burst_efficiency_table() -> None:
    """Print burst efficiency for queue depths 1–50, 64-byte frames."""
    print("=" * 76)
    print("FRAME BURSTING EFFICIENCY — 64-byte frames (46-byte payload each)")
    print(
        f"IFE fill = {IFE_BYTES} B per gap  |  burst cap = {BURST_CAP_BYTES:,} B"
        f"  |  CE-only baseline = 9%"
    )
    print("-" * 76)
    print(
        f"{'Queue':>7} | {'In burst':>8} | {'Wire (B)':>10} | "
        f"{'Payload (B)':>11} | {'Burst eff.':>11} | {'vs CE-only'}"
    )
    print("-" * 76)
    depths = list(range(1, 11)) + [15, 20, 30, 50]
    for n in depths:
        r = frame_burst_efficiency(n, 64)
        ratio = r.burst_efficiency / r.ce_solo_efficiency
        cap_mark = " *" if r.burst_cap_exceeded else "  "
        print(
            f"{n:>7} | {r.frames_in_burst:>8} | {r.wire_bytes:>10,} | "
            f"{r.total_payload_bytes:>11,} | {r.burst_efficiency:>10.1%} | "
            f"{ratio:>6.1f}×{cap_mark}"
        )

    print()
    print("  * Burst cap reached; remaining frames start a new burst.")
    print()

    # Worked example verbatim from lesson prose: 20 × 64-byte frames
    N = 20
    r = frame_burst_efficiency(N, 64)
    ce1 = max(64, CE_MIN_WIRE_BYTES)
    ife_total = (N - 1) * IFE_BYTES
    rest_frames = (N - 1) * 64
    total = ce1 + ife_total + rest_frames
    print("  WORKED EXAMPLE: 20 queued 64-byte frames")
    print(f"    Frame 1 (CE-padded) : {ce1} bytes")
    print(f"    Frames 2-20         : 19 × 64 = {rest_frames} bytes")
    print(f"    IFE fill (19 gaps)  : 19 × {IFE_BYTES} = {ife_total} bytes")
    print(f"    Total wire bytes    : {ce1} + {rest_frames} + {ife_total} = {total} bytes")
    print(f"    Total payload       : 20 × 46 = {N * 46} bytes")
    print(
        f"    Burst efficiency    : {N * 46} / {total} = "
        f"{N * 46 / total:.1%}"
    )
    print(
        f"    CE-only baseline    : {r.ce_solo_efficiency:.0%}  "
        f"→ {r.burst_efficiency / r.ce_solo_efficiency:.0f}× improvement"
    )
    print()


# ---------------------------------------------------------------------------
# 4. Encoding overhead comparison
# ---------------------------------------------------------------------------

def bandwidth_overhead_table() -> None:
    """Print Manchester / 4B5B / 8B10B / 64B66B encoding overhead."""
    print("=" * 76)
    print("ENCODING OVERHEAD COMPARISON")
    print("-" * 76)
    print(
        f"{'Encoding':>12} | {'Standard':>16} | {'d:c':>5} | "
        f"{'Overhead':>9} | {'Baud rate':>14} | DC balance"
    )
    print("-" * 76)

    rows = [
        # (name, standard, data_bits, code_bits, data_rate_bps, dc_method)
        ("Manchester",  "10BASE-T",         1,  2,     10e6, "by construction"),
        ("4B/5B",       "100BASE-TX",        4,  5,    100e6, "NRZI + scrambler"),
        ("8B/10B",      "1000Base-SX/LX/CX", 8, 10,  1000e6, "running disparity"),
        ("64B/66B",     "10GBase-SR/LR",    64, 66, 10_000e6, "scrambler"),
    ]

    for name, std, d, c, rate_bps, dc in rows:
        overhead = (c - d) / d * 100
        baud = rate_bps * c / d
        if baud >= 1e9:
            baud_str = f"{baud / 1e9:.3f} Gbaud"
        else:
            baud_str = f"{baud / 1e6:.0f} Mbaud"
        print(
            f"{name:>12} | {std:>16} | {d:>1}:{c:<2} | "
            f"{overhead:>8.1f}% | {baud_str:>14} | {dc}"
        )

    print()
    print("  8B/10B guarantees ≤ 6 consecutive equal bits (clock recovery)")
    print("  and holds running disparity within ±1 (DC balance on fiber/copper).")
    print("  64B/66B achieves < 3.2% overhead using a scrambler for DC balance.")
    print()


# ---------------------------------------------------------------------------
# 5. 8B/10B running-disparity demonstration
# ---------------------------------------------------------------------------

def eightb10b_running_disparity_demo() -> None:
    """Illustrate 8B/10B encoding and running-disparity tracking.

    Each data byte maps to two 10-bit codewords (RD− and RD+).  The encoder
    picks the variant that steers the running tally of 1s vs 0s back toward
    zero, keeping DC balance over the wire.
    """
    print("=" * 76)
    print("8B/10B RUNNING DISPARITY — Principle and Stream Trace")
    print("(RD− used when disparity is −1; RD+ used when disparity is +1)")
    print("-" * 76)

    # Subset of the 8B/10B encoding table (IEEE 802.3z uses the X3.230 table)
    # Columns: (hex value, name, RD− 10-bit word, RD+ 10-bit word)
    table: list[tuple[int, str, int, int]] = [
        (0x00, "D0.0",  0b1001110100, 0b0110001011),
        (0x07, "D7.0",  0b1110101000, 0b0001010111),
        (0x1C, "D28.0", 0b0011100100, 0b1100011011),
        (0xBC, "K28.5", 0b0011111010, 0b1100000101),  # comma / sync character
        (0xF4, "K28.1", 0b0011111001, 0b1100000110),  # idle fill (K28.1)
        (0xFF, "D31.7", 0b1010111100, 0b0101000011),
    ]

    print(
        f"  {'Value':>7} | {'Name':>6} | {'RD− (10 bits)':>13} | "
        f"{'RD+ (10 bits)':>13} | {'Ones−':>5} | {'Ones+':>5}"
    )
    print(f"  {'-'*7} | {'-'*6} | {'-'*13} | {'-'*13} | {'-'*5} | {'-'*5}")
    for bval, name, rd_m, rd_p in table:
        print(
            f"  0x{bval:02X}    | {name:>6} | {rd_m:010b}    | "
            f"{rd_p:010b}    | {bin(rd_m).count('1'):>5} | {bin(rd_p).count('1'):>5}"
        )

    print()
    print("  STREAM TRACE: K28.5, D0.0, D7.0  (starting with RD = −1)")
    print(f"  {'Symbol':>6} | {'Chosen':>4} | {'10-bit codeword':>16} | "
          f"{'1s':>3} | {'0s':>3} | {'RD after'}")
    print(f"  {'-'*6} | {'-'*4} | {'-'*16} | {'-'*3} | {'-'*3} | {'-'*8}")

    stream = [
        ("K28.5", 0b0011111010, 0b1100000101),
        ("D0.0",  0b1001110100, 0b0110001011),
        ("D7.0",  0b1110101000, 0b0001010111),
    ]
    rd = -1
    for name, rd_minus, rd_plus in stream:
        chosen = rd_minus if rd == -1 else rd_plus
        label = "RD−" if rd == -1 else "RD+"
        ones = bin(chosen).count('1')
        zeros = 10 - ones
        disparity = ones - zeros
        rd = 1 if disparity > 0 else -1
        print(
            f"  {name:>6} | {label:>4} | {chosen:016b} | "
            f"{ones:>3} | {zeros:>3} | {rd:+d}"
        )

    print()
    print("  After each codeword the encoder flips to the opposite variant,")
    print("  bounding the running tally within ±1 and preventing DC buildup.")
    print()


# ---------------------------------------------------------------------------
# 6. PAUSE frame structure and timing
# ---------------------------------------------------------------------------

def pause_frame_demo() -> None:
    """Print PAUSE frame fields and pause-duration table at 1 Gbps."""
    print("=" * 76)
    print("IEEE 802.3x PAUSE FRAME — Structure and Timing at 1 Gbps")
    print("-" * 76)
    unit_ns = SLOT_BITS  # 1 pause unit = 512 bit-times = 512 ns at 1 Gbps

    print(f"  Destination  : 01:80:C2:00:00:01  (reserved multicast, never forwarded)")
    print(f"  EtherType    : 0x8808  (MAC Control)")
    print(f"  Opcode       : 0x0001  (PAUSE)")
    print(f"  Quanta unit  : {unit_ns} ns  (= 512 bit-times at 1 Gbps)")
    print()
    print(f"  {'Quanta':>10} | {'Duration (ms)':>14} | Description")
    print(f"  {'-'*10} | {'-'*14} | {'-'*40}")
    entries = [
        (0,     "release: resume immediately"),
        (1,     "1 slot time (512 ns)"),
        (1000,  "moderate back-pressure"),
        (10000, "heavy congestion signal"),
        (65535, "maximum pause (≈ 33.5 ms)"),
    ]
    for quanta, desc in entries:
        dur_ms = quanta * unit_ns / 1e6
        print(f"  {quanta:>10} | {dur_ms:>14.3f} | {desc}")

    max_ms = 65535 * unit_ns / 1e6
    print()
    print(f"  Maximum suppression: 65535 × 512 ns = {max_ms:.1f} ms")
    print("  PAUSE halts ALL traffic from the remote end (priority-blind).")
    print("  IEEE 802.1Qbb Priority-based Flow Control (2011) adds per-queue control.")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print_slot_time_table()
    print_ce_efficiency_table()
    print_burst_efficiency_table()
    bandwidth_overhead_table()
    eightb10b_running_disparity_demo()
    pause_frame_demo()

    print("=" * 76)
    print("SUMMARY")
    print("-" * 76)
    r46 = carrier_extension_efficiency(46)
    r20 = frame_burst_efficiency(20, 64)
    print(f"  Slot time (1 Gbps)         : {SLOT_BITS} bit-times = {SLOT_BITS} ns")
    print(f"  Half-duplex limit (cable)  : ~45 m; ~25 m practical (incl. NIC delays)")
    print(f"  With carrier extension     : slot = 4096 ns → ~200 m practical")
    print(f"  CE efficiency (46 B pay.)  : {r46.payload_efficiency:.0%}  "
          f"(≈ 90 Mbps useful at 1 Gbps)")
    print(f"  Burst efficiency (20×64 B) : {r20.burst_efficiency:.0%}  "
          f"(≈ {r20.burst_efficiency / r46.payload_efficiency:.0f}× vs CE-only)")
    print(f"  8B/10B overhead            : 25%  → 1.25 Gbaud for 1 Gbps data")
    print(f"  Burst cap                  : {BURST_CAP_BYTES:,} bytes")
    print()
    print("  Carrier extension and frame bursting apply only in half-duplex hub mode.")
    print("  Full-duplex switched Ethernet never adds extension bytes — switches are")
    print("  the reason carrier extension became a historical footnote by 2005.")


if __name__ == "__main__":
    main()
