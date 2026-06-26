"""Bit stuffing with HDLC flags.

A runnable, stdlib-only demonstration of:
  * the HDLC bit-stuffing rule (insert a 0 after five consecutive 1s),
  * the inverse destuffing rule,
  * flag scanning and abort detection,
  * a full HDLC frame parser (Flag/Address/Control/Info/FCS/Flag),
  * a resynchronization test showing recovery after a corrupted bit.

Run with:  python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field

HDLC_FLAG = [0, 1, 1, 1, 1, 1, 1, 0]  # 0x7E
ABORT_RUN = 6  # six consecutive 1s is an abort, not data


# ---------------------------------------------------------------------------
# Core bit-stuffing primitives
# ---------------------------------------------------------------------------

def stuff(bits: list[int]) -> list[int]:
    """Apply HDLC bit stuffing: insert a 0 after every five consecutive 1s.

    The flag pattern (six 1s) can therefore never appear in the output.
    """
    out: list[int] = []
    ones = 0
    for b in bits:
        out.append(b)
        if b == 1:
            ones += 1
            if ones == 5:
                out.append(0)  # stuff
                ones = 0
        else:
            ones = 0
    return out


def destuff(bits: list[int]) -> tuple[list[int], list[int]]:
    """Inverse of stuff().

    Returns (destuffed, residual) where residual is any trailing bits that
    were not followed by enough data to decide (e.g. a partial run at EOF).
    Five 1s followed by a 0 -> drop the 0.
    Five 1s followed by a 1 -> that is a flag or abort; stop destuffing data
    and leave the boundary for the flag scanner to handle.
    """
    out: list[int] = []
    ones = 0
    i = 0
    n = len(bits)
    while i < n:
        b = bits[i]
        if ones == 5:
            if b == 0:
                ones = 0  # destuff: drop this 0
                i += 1
                continue
            else:
                # five 1s then a 1 -> flag/abort boundary; stop here
                break
        out.append(b)
        if b == 1:
            ones += 1
        else:
            ones = 0
        i += 1
    residual = bits[i:]
    return out, residual


def find_flags(bits: list[int]) -> list[int]:
    """Return start indices of every 01111110 flag in the bit stream."""
    flags: list[int] = []
    target = HDLC_FLAG
    m = len(target)
    for i in range(len(bits) - m + 1):
        if bits[i:i + m] == target:
            flags.append(i)
    return flags


def detect_aborts(bits: list[int]) -> list[int]:
    """Return start indices of every run of >=6 consecutive 1s."""
    aborts: list[int] = []
    ones = 0
    start = 0
    for i, b in enumerate(bits):
        if b == 1:
            if ones == 0:
                start = i
            ones += 1
            if ones == ABORT_RUN:
                aborts.append(start)
        else:
            ones = 0
    return aborts


# ---------------------------------------------------------------------------
# HDLC frame model
# ---------------------------------------------------------------------------

@dataclass
class HDLCFrame:
    flag_open: list[int]
    address: list[int]
    control: list[int]
    information: list[int]
    fcs: list[int]
    flag_close: list[int]
    raw: list[int] = field(default_factory=list)

    @property
    def control_type(self) -> str:
        c = self.control
        if not c:
            return "?"
        if c[0] == 0:
            return "I-frame (information)"
        if len(c) >= 2 and c[0] == 1 and c[1] == 0:
            return "S-frame (supervisory)"
        return "U-frame (unnumbered)"

    def __repr__(self) -> str:
        return (
            f"HDLCFrame(type={self.control_type}, "
            f"addr={_to_str(self.address)}, ctrl={_to_str(self.control)}, "
            f"info_len={len(self.information)} bits, "
            f"fcs={_to_str(self.fcs)})"
        )


def build_frame(address: int, control: int, info: list[int],
                fcs_bits: int = 16) -> HDLCFrame:
    """Build an HDLC frame from integer address/control fields.

    The FCS is a placeholder pseudo-CRC (pattern of 1s/0s) so the demo can
    focus on framing; a real implementation runs CRC-CCITT (0x1021) over
    the pre-stuffed Address+Control+Information bits.
    """
    addr_bits = _int_to_bits(address, 8)
    ctrl_bits = _int_to_bits(control, 8)
    fcs = [1, 0, 1, 0, 1, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 0][:fcs_bits]
    body = addr_bits + ctrl_bits + info + fcs
    stuffed = stuff(body)
    raw = HDLC_FLAG + stuffed + HDLC_FLAG
    return HDLCFrame(
        flag_open=HDLC_FLAG,
        address=addr_bits,
        control=ctrl_bits,
        information=info,
        fcs=fcs,
        flag_close=HDLC_FLAG,
        raw=raw,
    )


def parse_frame(raw: list[int]) -> HDLCFrame | None:
    """Parse one HDLC frame from raw bits that begin and end with a flag.

    Strips the flags, destuffs the body, then slices out the fields using
    the standard layout: Address(8) Control(8) Info(...) FCS(16).
    """
    flags = find_flags(raw)
    if len(flags) < 2:
        return None
    start, end = flags[0], flags[1]
    body_on_line = raw[start + 8:end]
    body, _ = destuff(body_on_line)
    if len(body) < 8 + 8 + 16:
        return None
    address = body[0:8]
    control = body[8:16]
    fcs = body[-16:]
    info = body[16:-16]
    return HDLCFrame(
        flag_open=raw[start:start + 8],
        address=address,
        control=control,
        information=info,
        fcs=fcs,
        flag_close=raw[end:end + 8],
        raw=raw[start:end + 8],
    )


def _int_to_bits(value: int, width: int) -> list[int]:
    return [(value >> (width - 1 - i)) & 1 for i in range(width)]


def _to_str(bits: list[int]) -> str:
    return "".join(str(b) for b in bits)


def stuffed_positions(original: list[int], on_line: list[int]) -> list[int]:
    """Return the indices (in on_line) of inserted stuffed 0 bits."""
    positions: list[int] = []
    oi = 0
    ones = 0
    for li, b in enumerate(on_line):
        if oi < len(original) and b == original[oi]:
            if b == 1:
                ones += 1
            else:
                ones = 0
            oi += 1
        else:
            # b is a stuffed 0 inserted right after five 1s
            positions.append(li)
            ones = 0
    return positions


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_textbook_fig_3_5() -> None:
    print("=== Textbook Fig. 3-5 trace ===")
    original = [0, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
                1, 1, 1, 1, 0, 0, 1, 0]
    on_line = stuff(original)
    recovered, _ = destuff(on_line)
    print(f"(a) original : {_to_str(original)}")
    print(f"(b) on line  : {_to_str(on_line)}")
    print(f"(c) stored   : {_to_str(recovered)}")
    print(f"stuffed bits : {len(on_line) - len(original)} "
          f"at on-line positions {stuffed_positions(original, on_line)}")
    print(f"round-trip OK: {recovered == original}")
    print()


def demo_frame_parse() -> None:
    print("=== HDLC frame build + parse ===")
    info = [1, 0, 1, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1, 1, 0, 0]  # 16 payload bits
    frame = build_frame(address=0x01, control=0x00, info=info)
    print(f"raw frame ({len(frame.raw)} bits): {_to_str(frame.raw)}")
    print(f"  open flag : {_to_str(frame.flag_open)} (0x7E)")
    print(f"  address   : {_to_str(frame.address)} (0x01)")
    print(f"  control   : {_to_str(frame.control)} -> {frame.control_type}")
    print(f"  info      : {_to_str(frame.information)} ({len(frame.information)} bits)")
    print(f"  fcs       : {_to_str(frame.fcs)}")
    print(f"  close flag: {_to_str(frame.flag_close)} (0x7E)")

    parsed = parse_frame(frame.raw)
    print(f"\nparsed back: {parsed}")
    print(f"  info recovered intact: {parsed is not None and parsed.information == info}")
    print()


def demo_worst_case_expansion() -> None:
    print("=== Worst-case expansion ===")
    for n in (8, 80, 800, 8000):
        all_ones = [1] * n
        stuffed = stuff(all_ones)
        ratio = len(stuffed) / n
        print(f"  {n:5d} bits of all-1s -> {len(stuffed):5d} on line "
              f"(expansion {ratio:.3f}x, ~{(ratio - 1) * 100:.1f}%)")
    print()


def demo_resync_after_error() -> None:
    print("=== Resynchronization after a bit error ===")
    info = [1, 0, 1, 1, 0, 1, 1, 1, 1, 1, 0, 0, 1, 0, 1, 1] * 2
    frame = build_frame(address=0x03, control=0x00, info=info)
    raw = list(frame.raw)
    body_start = 8
    raw[body_start + 3] ^= 1  # corrupt one payload bit inside the body
    flags = find_flags(raw)
    print(f"corrupted frame, flags found at: {flags}")
    print("a byte-count receiver would now be lost; a bit-stuffing")
    print("receiver scans forward to the next real flag and re-anchors.")
    recovered = parse_frame(raw)
    print(f"re-parsed (CRC would fail, but framing re-syncs): {recovered is not None}")
    print()


def demo_abort_detection() -> None:
    print("=== Abort sequence detection ===")
    payload = [1, 1, 1, 1, 1, 1, 1]  # seven 1s
    stuffed_stream = HDLC_FLAG + stuff(payload) + HDLC_FLAG
    # A real abort is sent UNSTUFFED: six+ 1s on the line.
    raw_abort = HDLC_FLAG + [1] * 7 + HDLC_FLAG
    print(f"stuffed payload stream : {_to_str(stuffed_stream)}")
    print(f"raw abort stream       : {_to_str(raw_abort)}")
    print(f"aborts in stuffed data : {detect_aborts(stuffed_stream)} (none expected)")
    print(f"aborts in raw abort    : {detect_aborts(raw_abort)}")
    print()


def main() -> None:
    demo_textbook_fig_3_5()
    demo_frame_parse()
    demo_worst_case_expansion()
    demo_resync_after_error()
    demo_abort_detection()
    print("All demos complete.")


if __name__ == "__main__":
    main()
