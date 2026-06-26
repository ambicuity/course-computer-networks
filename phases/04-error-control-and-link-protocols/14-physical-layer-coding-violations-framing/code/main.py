"""Physical-layer coding violations for frame delimiting.

Stdlib-only demonstration of 4B/5B line coding (FDDI / 100BASE-X), its
reserved control symbols (J, K, T, R, I, H, Q), and how an FDDI frame is
delimited by coding violations alone -- no byte or bit stuffing.

Also includes a 64B/66B sync-header block encoder (10GBASE-R) to show the
positional-header style of coding violation used at higher speeds.

Run:  python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# 4B/5B tables (ANSI X3T9.5 / FDDI). 4 data bits -> 5 line bits.
# ---------------------------------------------------------------------------

DATA_4B5B: Dict[int, str] = {
    0x0: "11110", 0x1: "01001", 0x2: "10100", 0x3: "10101",
    0x4: "01010", 0x5: "01011", 0x6: "01110", 0x7: "01111",
    0x8: "10010", 0x9: "10011", 0xA: "10110", 0xB: "10111",
    0xC: "11010", 0xD: "11011", 0xE: "11100", 0xF: "11101",
}

# Reserved control symbols. None of these codewords appear in DATA_4B5B.
CONTROL_4B5B: Dict[str, str] = {
    "I": "11111",  # Idle
    "H": "00100",  # Halt
    "J": "11000",  # Start delimiter byte 1 (coding violation)
    "K": "10001",  # Start delimiter byte 2 (coding violation)
    "T": "01101",  # End delimiter byte 1
    "R": "00111",  # End delimiter byte 2 / reset
    "Q": "00000",  # Quiet
}

# Reverse lookup: 5-bit string -> ("data", nibble) or ("control", name)
_LINE_TO_SYMBOL: Dict[str, Tuple[str, str]] = {}
for _nibble, _code in DATA_4B5B.items():
    _LINE_TO_SYMBOL[_code] = ("data", f"{_nibble:X}")
for _name, _code in CONTROL_4B5B.items():
    _LINE_TO_SYMBOL[_code] = ("control", _name)


def encode_4b5b(data: bytes) -> str:
    """Encode a byte string into a 4B/5B line-bit string.

    Each byte yields two 5-bit codewords (high nibble then low nibble).
    Only data codewords are ever produced -- control symbols cannot
    appear, which is what makes J/K/T/R usable as delimiters.
    """
    out: List[str] = []
    for byte in data:
        hi = (byte >> 4) & 0xF
        lo = byte & 0xF
        out.append(DATA_4B5B[hi])
        out.append(DATA_4B5B[lo])
    return "".join(out)


def _split5(s: str) -> List[str]:
    return [s[i:i + 5] for i in range(0, len(s) - 4, 5)]


def decode_4b5b(line_bits: str) -> Tuple[List[Tuple[str, str]], List[str]]:
    """Decode a 5B-aligned bit stream into a list of (kind, value) symbols.

    Returns (symbols, errors). Symbols with no table entry (the truly
    illegal codewords like 11001) are reported as errors.
    """
    symbols: List[Tuple[str, str]] = []
    errors: List[str] = []
    for chunk in _split5(line_bits):
        entry = _LINE_TO_SYMBOL.get(chunk)
        if entry is None:
            errors.append(chunk)
            symbols.append(("illegal", chunk))
        else:
            symbols.append(entry)
    return symbols, errors


def build_fddi_frame(payload: bytes) -> str:
    """Build an FDDI-style frame delimited by J,K ... T,R coding violations.

    Structure:  I* | J K | payload(4B/5B) | T R | I*
    The delimiters are reserved control symbols: no stuffing is applied
    to the payload because the encoder cannot emit J/K from any data nibble.
    """
    idle = CONTROL_4B5B["I"] * 4  # a few idle symbols before/after
    start = CONTROL_4B5B["J"] + CONTROL_4B5B["K"]
    end = CONTROL_4B5B["T"] + CONTROL_4B5B["R"]
    return idle + start + encode_4b5b(payload) + end + idle


def scan_for_frame(line_bits: str) -> Tuple[int, int, str]:
    """Scan a bit stream for an FDDI frame delimited by J,K ... T.

    Returns (start_index, end_index, payload_bits). If no frame is found,
    returns (-1, -1, ""). Demonstrates resync: the receiver simply hunts
    for the reserved J,K pair -- no length field, no stuffing to undo.
    """
    jk = CONTROL_4B5B["J"] + CONTROL_4B5B["K"]
    t = CONTROL_4B5B["T"]
    start = line_bits.find(jk)
    if start < 0:
        return -1, -1, ""
    payload_start = start + len(jk)
    end = line_bits.find(t, payload_start)
    if end < 0:
        return start, -1, ""
    return start, end, line_bits[payload_start:end]


# ---------------------------------------------------------------------------
# 64B/66B block (10GBASE-R) -- positional sync header as coding violation.
# ---------------------------------------------------------------------------

@dataclass
class Block66B:
    """A 64B/66B block: 2-bit sync header + 64-bit payload.

    Sync header '01' => data block (8 data bytes).
    Sync header '10' => control block.
    Headers '00' and '11' are errors. The header is positional and never
    part of the payload, so no stuffing is required.
    """
    is_control: bool
    payload: bytes  # exactly 8 bytes

    def __post_init__(self) -> None:
        if len(self.payload) != 8:
            raise ValueError("64B/66B payload must be exactly 8 bytes")

    def sync_header(self) -> str:
        return "10" if self.is_control else "01"

    def to_bits(self) -> str:
        return self.sync_header() + "".join(f"{b:08b}" for b in self.payload)

    @classmethod
    def from_bits(cls, bits: str) -> "Block66B":
        if len(bits) != 66:
            raise ValueError("expected 66 bits")
        header = bits[:2]
        if header == "01":
            is_control = False
        elif header == "10":
            is_control = True
        else:
            raise ValueError(f"invalid sync header {header} (must be 01 or 10)")
        payload = bytes(int(bits[i:i + 8], 2) for i in range(2, 66, 8))
        return cls(is_control=is_control, payload=payload)


# ---------------------------------------------------------------------------
# Overhead comparison: coding violation vs byte/bit stuffing.
# ---------------------------------------------------------------------------

def byte_stuff_overhead(payload: bytes, flag: int = 0x7E, esc: int = 0x7D) -> int:
    """Return the stuffed length of a PPP-style byte-stuffed payload.

    Each flag or escape byte in the payload is prefixed with ESC, so the
    worst case doubles the payload. Coding-violation framing has zero
    stuffing overhead.
    """
    stuffed = 0
    for b in payload:
        if b in (flag, esc):
            stuffed += 2  # ESC + the escaped byte
        else:
            stuffed += 1
    return stuffed


def framing_overhead(payload: bytes) -> Dict[str, float]:
    """Compute framing overhead fractions for three methods on one payload."""
    n = len(payload) * 8  # payload bits
    # 4B/5B + J,K + T,R: payload*5/4 line bits + 4 control symbols * 5 bits
    line_4b5b = n * 5 // 4 + 4 * 5
    # Byte stuffing: stuffed bytes * 8 + flag overhead (2 flags) * 8
    stuffed_bytes = byte_stuff_overhead(payload)
    line_bytestuff = stuffed_bytes * 8 + 2 * 8
    # Bit stuffing (HDLC): up to 1 stuffed bit per 5 ones; approximate 12.5%
    line_bitstuff = n + n // 8 + 2 * 8
    return {
        "4B/5B + coding-violation delimiters": (line_4b5b - n) / n,
        "byte stuffing (PPP)": (line_bytestuff - n) / n,
        "bit stuffing (HDLC, est.)": (line_bitstuff - n) / n,
    }


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

SAMPLE_PAYLOAD = bytes([0xFF, 0x00, 0x7E, 0x7E, 0x55, 0xAA, 0x7E, 0x01])


def print_table() -> None:
    print("=== 4B/5B data table ===")
    for nibble, code in DATA_4B5B.items():
        print(f"  {nibble:X} -> {code}")
    print("\n=== 4B/5B control / reserved symbols ===")
    data_codes = set(DATA_4B5B.values())
    for name, code in CONTROL_4B5B.items():
        in_data = code in data_codes
        tag = "  (ALSO DATA? bug)" if in_data else "  (reserved - not in data)"
        print(f"  {name} -> {code}{tag}")
    for name, code in CONTROL_4B5B.items():
        assert code not in data_codes, f"{name} collides with a data codeword!"
    print("\nInvariant holds: no control symbol is representable as data.")


def print_frame_demo() -> None:
    print("\n=== FDDI frame with coding-violation delimiters ===")
    print(f"Payload bytes : {SAMPLE_PAYLOAD.hex(' ')}")
    frame = build_fddi_frame(SAMPLE_PAYLOAD)
    print(f"Line bits     : {frame}")
    symbols, errors = decode_4b5b(frame)
    pretty = " ".join(f"{v}:{k[0].upper()}" for k, v in symbols)
    print(f"Symbols       : {pretty}")
    print(f"Decode errors : {errors if errors else 'none'}")

    start, end, payload_bits = scan_for_frame(frame)
    print("\nScanner (hunts for reserved J,K ... T pair):")
    print(f"  start index : {start}")
    print(f"  end index   : {end}")
    print(f"  payload bits: {payload_bits}")

    # Transparency check: a tricky payload must not produce J or K.
    tricky = bytes([0xC3, 0x1F])  # nibbles C,3,1,F
    enc = encode_4b5b(tricky)
    assert "11000" not in _split5(enc), "unexpected J in data encoding"
    assert "10001" not in _split5(enc), "unexpected K in data encoding"
    print(f"\nTransparency: payload {tricky.hex()} -> {enc} (no J/K produced)")


def print_66b_demo() -> None:
    print("\n=== 64B/66B block (10GBASE-R) ===")
    data_block = Block66B(is_control=False, payload=b"\x01\x02\x03\x04\x05\x06\x07\x08")
    ctrl_block = Block66B(is_control=True, payload=b"\x00\x00\x00\x00\x00\x00\x00\x00")
    print(f"Data block    : header={data_block.sync_header()} bits={data_block.to_bits()}")
    print(f"Control block : header={ctrl_block.sync_header()} bits={ctrl_block.to_bits()}")
    rt = Block66B.from_bits(data_block.to_bits())
    print(f"Round-trip    : control={rt.is_control} payload={rt.payload.hex()}")
    try:
        Block66B.from_bits("00" + "0" * 64)
    except ValueError as e:
        print(f"Invalid header '00' rejected: {e}")


def print_overhead_demo() -> None:
    print("\n=== Framing overhead comparison (1000-byte payloads) ===")
    payloads = {
        "all-0x00": b"\x00" * 1000,
        "all-0x7E": b"\x7E" * 1000,
        "random-ish": bytes((i * 37 + 11) & 0xFF for i in range(1000)),
    }
    for label, payload in payloads.items():
        print(f"\n  Payload: {label} ({len(payload)} bytes)")
        for method, frac in framing_overhead(payload).items():
            print(f"    {method:42s} overhead = {frac*100:6.2f}%")


def main() -> None:
    print_table()
    print_frame_demo()
    print_66b_demo()
    print_overhead_demo()
    print("\nDone. Delimiters J,K and T,R are coding violations: never stuffed.")


if __name__ == "__main__":
    main()
