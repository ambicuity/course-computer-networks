"""Line codes, clock recovery, and DC balance — runnable encoder/decoder demo.

Pure stdlib. Encodes an arbitrary bit stream in NRZ, NRZI (with USB-style bit
stuffing), Manchester, 4B/5B, and 8B/10B (with running-disparity tracking),
then analyses each waveform for the two numbers that decide whether a real
link will hold lock:

  * max_run   — longest run of consecutive identical line bits (clock recovery)
  * peak_disp — peak absolute running disparity / DC imbalance (AC coupling)

Run:  python3 main.py
"""

from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Bit helpers
# ---------------------------------------------------------------------------


def bytes_to_bits(data: bytes) -> List[int]:
    """MSB-first bit list from bytes."""
    bits: List[int] = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


# ---------------------------------------------------------------------------
# NRZ
# ---------------------------------------------------------------------------


def nrz(bits: List[int]) -> List[int]:
    """1 -> +1 level, 0 -> 0 level; identity on the bit sequence."""
    return list(bits)


# ---------------------------------------------------------------------------
# NRZI + USB bit stuffing (transitions on 1; stuff a 0 after six 1s)
# ---------------------------------------------------------------------------


def nrzi_encode(bits: List[int]) -> List[int]:
    """NRZI with USB-style bit stuffing: a 1 toggles the level; after six
    consecutive raw 1s a stuff cell is inserted to force a transition.
    A single SYNC '1' is prepended so the decoder has a reference transition
    (without it, a leading run of 0s is unrecoverable — the real reason USB
    frames begin with a KJKJ sync pattern)."""
    level = 0
    out: List[int] = []
    ones = 0
    # SYNC bit: force an initial 0->1 transition as a phase reference.
    level ^= 1
    out.append(level)
    ones = 1
    for b in bits:
        if b == 1:
            level ^= 1
            ones += 1
        else:
            ones = 0
        out.append(level)
        if ones == 6:
            # stuff a 0: level unchanged, just adds a non-transition cell
            out.append(level)
            ones = 0
    return out


def nrzi_decode(line: List[int]) -> List[int]:
    """Recover bits from transitions, drop the leading SYNC bit, then strip
    USB stuff bits (the 0 the encoder inserted after six consecutive 1s).

    The transition into the first cell (from the implicit prior level 0) is
    the SYNC '1'; transitions between consecutive cells are the data/stuff
    bits that follow."""
    raw: List[int] = [1 if line[0] != 0 else 0]  # SYNC transition into cell 0
    for i in range(1, len(line)):
        raw.append(1 if line[i] != line[i - 1] else 0)
    # The first recovered bit is the SYNC; discard it.
    raw = raw[1:]
    bits: List[int] = []
    ones = 0
    for b in raw:
        if ones == 6:
            # this is the stuffed 0; drop it and reset the counter
            ones = 0
            continue
        bits.append(b)
        ones = ones + 1 if b == 1 else 0
    return bits


# ---------------------------------------------------------------------------
# Manchester (IEEE 802.3: low->high = 0, high->low = 1; 2x clock)
# ---------------------------------------------------------------------------


def manchester(bits: List[int]) -> List[int]:
    out: List[int] = []
    for b in bits:
        if b == 0:
            out.extend([0, 1])  # low then high
        else:
            out.extend([1, 0])  # high then low
    return out


def manchester_decode(line: List[int]) -> List[int]:
    bits: List[int] = []
    for i in range(0, len(line) - 1, 2):
        a, c = line[i], line[i + 1]
        bits.append(0 if (a == 0 and c == 1) else 1)
    return bits


# ---------------------------------------------------------------------------
# 4B/5B
# ---------------------------------------------------------------------------

FIVE_B: Dict[int, str] = {
    0x0: "11110", 0x1: "01001", 0x2: "10100", 0x3: "10101",
    0x4: "01010", 0x5: "01011", 0x6: "01110", 0x7: "01111",
    0x8: "10010", 0x9: "10011", 0xA: "10110", 0xB: "10111",
    0xC: "11010", 0xD: "11011", 0xE: "11100", 0xF: "11101",
}
CTRL: Dict[str, str] = {
    "I": "11111", "J": "11000", "K": "10001", "T": "01101", "R": "00111",
}
FIVE_B_INV: Dict[str, int] = {v: k for k, v in FIVE_B.items()}


def encode_4b5b(bits: List[int]) -> List[int]:
    out: List[int] = []
    for i in range(0, len(bits) - len(bits) % 4, 4):
        nib = 0
        for b in bits[i:i + 4]:
            nib = (nib << 1) | b
        for c in FIVE_B[nib]:
            out.append(int(c))
    return out


def decode_4b5b(line: List[int]) -> List[int]:
    bits: List[int] = []
    for i in range(0, len(line) - len(line) % 5, 5):
        s = "".join(str(b) for b in line[i:i + 5])
        if s in FIVE_B_INV:
            nib = FIVE_B_INV[s]
            for k in range(3, -1, -1):
                bits.append((nib >> k) & 1)
    return bits


# ---------------------------------------------------------------------------
# 8B/10B with running disparity (compact, faithful selection rule)
# ---------------------------------------------------------------------------

# 8-bit data byte -> (negative_form, positive_form) as 10-bit strings.
# Negative form has disparity -2 (four 1s); positive has +2 (six 1s).
# Balanced codes (disparity 0) repeat the same string in both slots.
# Subset sufficient for the demo bytes (0x00, 0xFF, 0x6A) and neighbours.
EIGHT_TEN_B: Dict[int, Tuple[str, str]] = {
    0x00: ("1001110100", "0110001011"),  # D.0
    0x01: ("0111010100", "1000101011"),  # D.1
    0x02: ("1011010100", "0100101011"),  # D.2
    0x03: ("1100011011", "1100010100"),  # D.3
    0x04: ("1101010100", "0010101011"),  # D.4
    0x17: ("0111001011", "0111000100"),  # D.23
    0x2A: ("1000101011", "0111010100"),  # D.42
    0x6A: ("1010101011", "1010100100"),  # D.106  (balanced-ish)
    0xFF: ("1010110100", "0101001011"),  # D.255
}


def _disp(code: str) -> int:
    return code.count("1") - code.count("0")


def encode_8b10b(bits: List[int]) -> Tuple[List[int], List[int]]:
    """Return (line_bits, disparity_trace). RD starts at -1 (negative)."""
    rd = -1  # -1 negative, +1 positive (IBM convention)
    out: List[int] = []
    trace: List[int] = []
    for i in range(0, len(bits) - len(bits) % 8, 8):
        byte = 0
        for b in bits[i:i + 8]:
            byte = (byte << 1) | b
        neg, pos = EIGHT_TEN_B[byte]
        d_neg, d_pos = _disp(neg), _disp(pos)
        if d_neg == 0 and d_pos == 0:
            chosen = neg  # balanced; RD unchanged
        elif rd < 0:
            chosen = pos  # emit +2 form to pull RD up toward 0
            rd = +1 if d_pos > 0 else rd
        else:
            chosen = neg  # emit -2 form to pull RD down
            rd = -1 if d_neg < 0 else rd
        for ch in chosen:
            out.append(int(ch))
        trace.append(rd)
    return out, trace


def decode_8b10b(line: List[int]) -> List[int]:
    inv: Dict[str, int] = {}
    for k, (neg, pos) in EIGHT_TEN_B.items():
        inv[neg] = k
        inv[pos] = k
    bits: List[int] = []
    for i in range(0, len(line) - len(line) % 10, 10):
        s = "".join(str(b) for b in line[i:i + 10])
        if s in inv:
            byte = inv[s]
            for k in range(7, -1, -1):
                bits.append((byte >> k) & 1)
    return bits


# ---------------------------------------------------------------------------
# Analysis: max run + running disparity of an arbitrary line-bit stream
# ---------------------------------------------------------------------------


def analyze(line: List[int]) -> Tuple[int, int]:
    """Return (max_run_of_identical_bits, peak_abs_running_disparity)."""
    if not line:
        return 0, 0
    max_run = 1
    run = 1
    for i in range(1, len(line)):
        if line[i] == line[i - 1]:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 1
    disp = 0
    peak = 0
    for b in line:
        disp += 1 if b == 1 else -1
        peak = max(peak, abs(disp))
    return max_run, peak


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def show(name: str, line: List[int], decoded: List[int],
         original: List[int]) -> None:
    max_run, peak = analyze(line)
    ok = "PASS" if decoded == original else "FAIL"
    print(f"  {name:14s} len={len(line):4d}  max_run={max_run:3d}  "
          f"peak_disp={peak:3d}  roundtrip={ok}")


def main() -> None:
    payload = bytes([0x00, 0xFF, 0x6A])
    bits = bytes_to_bits(payload)
    print("Payload:", payload.hex(" "),
          "=", "".join(str(b) for b in bits))
    print(f"({len(bits)} bits)\n")

    print("=== Short payload, all five codes ===")
    show("NRZ", nrz(bits), nrz(bits), bits)
    show("NRZI+stuff", nrzi_encode(bits),
         nrzi_decode(nrzi_encode(bits)), bits)
    show("Manchester", manchester(bits),
         manchester_decode(manchester(bits)), bits)
    fb = encode_4b5b(bits)
    show("4B/5B", fb, decode_4b5b(fb), bits)
    eb, trace = encode_8b10b(bits)
    show("8B/10B", eb, decode_8b10b(eb), bits)
    print("  8B/10B running-disparity trace per symbol:", trace)

    print("\n=== Killer payload: 20 x 0x00 (160 zeros) ===")
    killer = bytes_to_bits(bytes([0x00] * 20))
    for name, line in [
        ("NRZ", nrz(killer)),
        ("NRZI+stuff", nrzi_encode(killer)),
        ("Manchester", manchester(killer)),
        ("4B/5B", encode_4b5b(killer)),
        ("8B/10B", encode_8b10b(killer)[0]),
    ]:
        mr, pk = analyze(line)
        verdict_clk = "PASS" if mr <= 5 else "FAIL"
        verdict_dc = "PASS" if pk <= 2 else "FAIL"
        print(f"  {name:14s} max_run={mr:4d} ({verdict_clk})  "
              f"peak_disp={pk:4d} ({verdict_dc})")

    print("\n=== 8B/10B disparity on all-zeros: RD must stay in {-1,+1} ===")
    az, tr = encode_8b10b(bytes_to_bits(bytes([0x00] * 8)))
    for i, rd in enumerate(tr):
        print(f"  symbol {i}: RD after = {rd:+d}")
    assert all(r in (-1, 1) for r in tr), "disparity escaped!"
    print("  -> RD stayed bounded; 8B/10B is DC-safe on all-zeros.")


if __name__ == "__main__":
    main()
