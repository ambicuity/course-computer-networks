"""SONET/SDH STS-1 frame model, overhead byte layout, and pointer/BIP-8 logic.

A stdlib-only simulator of the basic SONET STS-1 frame (ANSI T1.105 /
ITU-T G.707-G.709, the SDH family). It models the 90-column by 9-row,
810-byte frame emitted every 125 us (8000 frames/s, 51.84 Mbps gross), the
three overhead sublayers (Section / Line / Path), the H1/H2/H3 pointer that
lets the Synchronous Payload Envelope float and span frame boundaries, and
the BIP-8 parity bytes (B1, B2, B3) used for error monitoring.

No network calls, no third-party packages. Run:

    python3 code/main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- Fixed framing constants (ANSI T1.105, ITU-T G.707) ----------------------

FRAME_ROWS = 9
FRAME_COLS = 90                       # 3 overhead + 87 payload (SPE area)
FRAME_BYTES = FRAME_ROWS * FRAME_COLS  # 810
FRAME_PERIOD_US = 125                 # 1/8000 s
FRAMES_PER_SEC = 8_000
GROSS_RATE_MBPS = FRAME_BYTES * 8 * FRAMES_PER_SEC / 1e6   # 51.84

OVERHEAD_COLS = 3
SPE_COLS = FRAME_COLS - OVERHEAD_COLS                       # 87
SPE_BYTES = FRAME_ROWS * SPE_COLS                          # 783
SPE_RATE_MBPS = SPE_BYTES * 8 * FRAMES_PER_SEC / 1e6       # 50.112
PATH_OH_BYTES = FRAME_ROWS                                 # 1 col of SPE
USER_BYTES = FRAME_ROWS * (SPE_COLS - 1)                   # 774
USER_RATE_MBPS = USER_BYTES * 8 * FRAMES_PER_SEC / 1e6     # 49.536
OVERHEAD_RATE_MBPS = (FRAME_BYTES - SPE_BYTES) * 8 * FRAMES_PER_SEC / 1e6

# Framing pattern the receiver hunts for (A1 A2).
A1 = 0xF6
A2 = 0x28

# Pointer offset bounds: SPE byte 0..782, measured from the byte after H3.
POINTER_MIN = 0
POINTER_MAX = SPE_BYTES - 1   # 782


# --- Overhead field registry ------------------------------------------------
# (row, col) are 1-indexed inside the 3-column overhead block (col 1..3).
# Names are the canonical SONET STS-1 section/line overhead byte names.

SECTION_OH: dict[tuple[int, int], str] = {
    (1, 1): "A1", (1, 2): "A2", (1, 3): "C1",
    (2, 1): "B1", (2, 2): "E1", (2, 3): "F1",
    (3, 1): "D1", (3, 2): "D2", (3, 3): "D3",
}

LINE_OH: dict[tuple[int, int], str] = {
    (4, 1): "H1", (4, 2): "H2", (4, 3): "H3",
    (5, 1): "B2", (5, 2): "K1", (5, 3): "K2",
    (6, 1): "D4", (6, 2): "D5", (6, 3): "D6",
    (7, 1): "D7", (7, 2): "D8", (7, 3): "D9",
    (8, 1): "D10", (8, 2): "D11", (8, 3): "D12",
    (9, 1): "S1/Z1", (9, 2): "Z2", (9, 3): "E2",
}

PATH_OH: list[str] = ["J1", "B3", "C2", "G1", "F2", "H4", "Z3", "Z4", "N1"]


@dataclass
class STS1Frame:
    """A single STS-1 frame as a 9x90 byte grid (row-major, col 0 = overhead)."""
    grid: list[list[int]] = field(
        default_factory=lambda: [[0] * FRAME_COLS for _ in range(FRAME_ROWS)]
    )
    pointer: int = 0  # H1/H2 offset of SPE start within the SPE area

    def set_overhead(self, row: int, col: int, value: int) -> None:
        """Set a byte in the 3-column overhead block (row, col 1-indexed)."""
        if not 0 <= value <= 0xFF:
            raise ValueError(f"byte must fit 8 bits, got {value}")
        self.grid[row - 1][col - 1] = value

    def get_overhead(self, row: int, col: int) -> int:
        return self.grid[row - 1][col - 1]

    def set_payload(self, row: int, payload_col: int, value: int) -> None:
        """Set a byte in the 87-column payload area (payload_col 1-indexed)."""
        if not 0 <= value <= 0xFF:
            raise ValueError(f"byte must fit 8 bits, got {value}")
        self.grid[row - 1][OVERHEAD_COLS + payload_col - 1] = value

    def payload_bytes(self) -> list[int]:
        out: list[int] = []
        for r in range(FRAME_ROWS):
            out.extend(self.grid[r][OVERHEAD_COLS:])
        return out


# --- Pointer (H1/H2/H3) machinery -------------------------------------------

def build_pointer_word(offset: int, ndf: bool = False) -> tuple[int, int]:
    """Encode the 16-bit H1/H2 pointer word.

    Layout: [NDF 4 bits][SS 2 bits][offset high 2 bits] in H1, [offset low 8]
    in H2. NDF normal = 0110; when the New Data Flag is set = 1001. SS = 10
    for STS-1. Real silicon interleaves I/D stuffing bits among the 10 offset
    value bits; here we keep the value field and simulate justification by
    +/-1 on the offset.
    """
    if not POINTER_MIN <= offset <= POINTER_MAX:
        raise ValueError(f"offset {offset} out of range {POINTER_MIN}..{POINTER_MAX}")
    ndf_field = 0b1001 if ndf else 0b0110
    ss_field = 0b10
    high = (offset >> 8) & 0x03
    low = offset & 0xFF
    h1 = (ndf_field << 4) | (ss_field << 2) | high
    h2 = low
    return h1, h2


def decode_pointer_word(h1: int, h2: int) -> tuple[int, bool]:
    """Decode H1/H2 back into (offset, ndf)."""
    ndf_field = (h1 >> 4) & 0x0F
    ndf = ndf_field == 0b1001
    high = h1 & 0x03
    offset = (high << 8) | h2
    return offset, ndf


def pointer_stuff(op: str, current: int) -> int:
    """Apply one pointer justification event and return the new offset.

    op = 'positive' (payload late: insert 1 stuff byte, offset +1)
         'negative' (payload early: carry a real byte in H3, offset -1)
    Positive stuffing: a dummy byte is inserted right after H3, so the SPE
    grows by one byte and the offset to the next SPE start increases by 1.
    Negative stuffing: the H3 byte carries a real payload byte, the SPE
    shrinks by one, and the offset decreases by 1.
    """
    if op == "positive":
        return min(POINTER_MAX, current + 1)
    if op == "negative":
        return max(POINTER_MIN, current - 1)
    raise ValueError(f"unknown stuff op {op!r}")


# --- BIP-8 error monitoring --------------------------------------------------

def bip8(blocks: list[int]) -> int:
    """Even-parity BIP-8: bit i = parity of bit i across all covered bytes."""
    parity = 0
    for b in blocks:
        parity ^= b
    return parity & 0xFF


# --- Construction helpers ----------------------------------------------------

def make_idle_frame(pointer: int = 0, c1: int = 1) -> STS1Frame:
    """Build an idle STS-1 frame: A1/A2 framing, a C1 STS-ID, rest 0."""
    f = STS1Frame(pointer=pointer)
    f.set_overhead(1, 1, A1)
    f.set_overhead(1, 2, A2)
    f.set_overhead(1, 3, c1)
    h1, h2 = build_pointer_word(pointer)
    f.set_overhead(4, 1, h1)
    f.set_overhead(4, 2, h2)
    return f


def fill_payload(frame: STS1Frame, payload: bytes) -> None:
    """Place payload bytes into the SPE area behind the path overhead column."""
    if len(payload) > USER_BYTES:
        raise ValueError(f"payload {len(payload)} exceeds SPE user capacity {USER_BYTES}")
    idx = 0
    for col in range(2, SPE_COLS + 1):  # payload col 1 is the path overhead
        for row in range(1, FRAME_ROWS + 1):
            if idx >= len(payload):
                return
            frame.set_payload(row, col, payload[idx])
            idx += 1


def locate_spe_start(offset: int) -> tuple[int, int]:
    """Map a pointer offset to a (row, payload_col) in the frame.

    The pointer counts bytes of the SPE area starting just after the H3 byte
    (row 4, col 3). The SPE area wraps across the row boundary, so an offset
    can land the SPE start mid-frame or make the SPE span two frames.
    """
    if not POINTER_MIN <= offset <= POINTER_MAX:
        raise ValueError("offset out of range")
    spe_row = (4 - 1 + (offset // SPE_COLS)) % FRAME_ROWS  # 0-indexed
    spe_col = offset % SPE_COLS                            # 0-indexed in SPE
    return spe_row + 1, spe_col + 1                        # 1-indexed


# --- Demo --------------------------------------------------------------------

def _print_overhead_layout() -> None:
    print("STS-1 overhead byte layout (rows x cols 1..3):\n")
    print("       c1   c2   c3")
    for r in range(1, FRAME_ROWS + 1):
        cells = []
        for c in range(1, 4):
            name = SECTION_OH.get((r, c)) or LINE_OH.get((r, c)) or "??"
            cells.append(f"{name:>4}")
        label = "SOH" if r <= 3 else "LOH"
        print(f" r{r} [{label}] " + "  ".join(cells))
    print(f"\nPath overhead (1st column of SPE): {' '.join(PATH_OH)}")


def _print_rate_budget() -> None:
    print("\nSTS-1 rate budget")
    print(f"  frame size        : {FRAME_BYTES} bytes = {FRAME_ROWS}x{FRAME_COLS}")
    print(f"  frame period      : {FRAME_PERIOD_US} us  ({FRAMES_PER_SEC} frames/s)")
    print(f"  gross rate        : {GROSS_RATE_MBPS:.3f} Mbps")
    print(f"  overhead (27 B)   : {OVERHEAD_RATE_MBPS:.3f} Mbps")
    print(f"  SPE   (783 B)     : {SPE_RATE_MBPS:.3f} Mbps  (line+section OH excluded)")
    print(f"  path OH (9 B)     : {PATH_OH_BYTES * 8 * FRAMES_PER_SEC / 1e6:.3f} Mbps")
    print(f"  user payload      : {USER_RATE_MBPS:.3f} Mbps  (774 B = 86 cols x 9 rows)")


def _demo_pointer() -> None:
    print("\nPointer demo (H1/H2 encodes the SPE start offset)")
    for off in (0, 1, 100, 522, 782):
        h1, h2 = build_pointer_word(off)
        back, _ = decode_pointer_word(h1, h2)
        row, col = locate_spe_start(off)
        print(f"  offset={off:3d}  H1=0x{h1:02X} H2=0x{h2:02X}  "
              f"decoded={back:3d}  SPE starts at row {row}, payload col {col}")
    print("\n  Justification: payload drifts early by one byte (negative stuffing)")
    cur = 522
    print(f"    offset {cur} -> {pointer_stuff('negative', cur)} (H3 carries a real byte)")
    print("  Justification: payload drifts late by one byte (positive stuffing)")
    print(f"    offset {cur} -> {pointer_stuff('positive', cur)} (a stuff byte is inserted)")


def _demo_bip8() -> None:
    print("\nBIP-8 demo: section B1 covers the previous frame's 810 bytes")
    f = make_idle_frame()
    fill_payload(f, bytes(i % 256 for i in range(USER_BYTES)))  # deterministic payload
    b1 = bip8(f.payload_bytes())
    print(f"  computed BIP-8 = 0x{b1:02X} (parity of bit k across all covered bytes)")
    tampered = STS1Frame(grid=[row[:] for row in f.grid])
    tampered.set_payload(1, 2, tampered.grid[0][OVERHEAD_COLS + 1] ^ 0x01)
    b1p = bip8(tampered.payload_bytes())
    print(f"  after 1-bit flip BIP-8 = 0x{b1p:02X}  -> mismatch flags a section error")


def _demo_spanning_spe() -> None:
    print("\nFloating SPE: an offset near the end makes the SPE span two frames")
    off = 780
    row, col = locate_spe_start(off)
    print(f"  offset={off}: SPE starts at row {row}, payload col {col}")
    print(f"  only {SPE_BYTES - off} bytes fit in this frame; the remaining "
          f"{off} bytes wrap into the NEXT frame's SPE area.")
    print("  This is why the SPE is 'floating' and pointed to, not fixed at row 1 col 4.")


def main() -> None:
    print("=" * 70)
    print(" SONET/SDH STS-1 Frame and Overhead")
    print("=" * 70)
    _print_overhead_layout()
    _print_rate_budget()
    _demo_pointer()
    _demo_bip8()
    _demo_spanning_spe()
    print("\nDone. See assets/sonet-sdh-sts-1-frame-and-overhead.svg for the layout.")


if __name__ == "__main__":
    main()
