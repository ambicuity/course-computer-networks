#!/usr/bin/env python3
"""Framing demonstrator: PPP byte stuffing and HDLC bit stuffing.

This is a self-contained, stdlib-only illustration of two of the four classic
data-link framing methods from Tanenbaum, Chapter 3, section 3.1.2:

  * PPP byte stuffing  (RFC 1662): flag 0x7E, escape 0x7D, transform XOR 0x20.
  * HDLC bit stuffing  (ISO/IEC 13239): flag 01111110, stuff a 0 after five 1s.

For each method we frame a payload, then unframe it, and assert the round trip
is transparent (unstuff(stuff(x)) == x) even for adversarial payloads built
entirely from flag bytes, escape bytes, or all-ones bits. We also report the
real overhead and compare it to the textbook worst case (~2x for byte stuffing,
~12.5% for bit stuffing).

Run:  python3 main.py
"""

from __future__ import annotations

# --- PPP / RFC 1662 constants -------------------------------------------------
PPP_FLAG = 0x7E          # frame delimiter
PPP_ESCAPE = 0x7D        # escape byte
PPP_XOR = 0x20           # transform applied to escaped bytes
# Async control characters (< 0x20) are escaped too; we use a default empty map
# meaning "escape only flag/escape" unless the caller asks for full escaping.

# --- HDLC constants -----------------------------------------------------------
HDLC_FLAG = "01111110"   # 0x7E as bits
STUFF_AFTER = 5          # stuff a 0 after this many consecutive 1s


# =============================================================================
# PPP byte stuffing (RFC 1662)
# =============================================================================
def ppp_stuff(payload: bytes, escape_control: bool = True) -> bytes:
    """Wrap *payload* in PPP flags, escaping flag/escape/control bytes.

    Each escaped byte B is emitted as ESCAPE followed by (B XOR 0x20).
    """
    out = bytearray([PPP_FLAG])
    for b in payload:
        needs_escape = b in (PPP_FLAG, PPP_ESCAPE) or (escape_control and b < 0x20)
        if needs_escape:
            out.append(PPP_ESCAPE)
            out.append(b ^ PPP_XOR)
        else:
            out.append(b)
    out.append(PPP_FLAG)
    return bytes(out)


def ppp_unstuff(frame: bytes) -> bytes:
    """Recover the original payload from a PPP-framed byte sequence."""
    if len(frame) < 2 or frame[0] != PPP_FLAG or frame[-1] != PPP_FLAG:
        raise ValueError("frame must start and end with the PPP flag 0x7E")
    body = frame[1:-1]
    out = bytearray()
    i = 0
    while i < len(body):
        b = body[i]
        if b == PPP_ESCAPE:
            i += 1
            if i >= len(body):
                raise ValueError("dangling escape byte at end of frame")
            out.append(body[i] ^ PPP_XOR)
        elif b == PPP_FLAG:
            raise ValueError("unescaped flag byte found inside frame body")
        else:
            out.append(b)
        i += 1
    return bytes(out)


# =============================================================================
# HDLC bit stuffing (ISO/IEC 13239)
# =============================================================================
def hdlc_stuff(data_bits: str) -> str:
    """Frame a bit string with HDLC flags and stuff a 0 after five 1s.

    *data_bits* is a string of '0'/'1'. Returns flag + stuffed-data + flag.
    """
    stuffed = []
    ones = 0
    for bit in data_bits:
        stuffed.append(bit)
        if bit == "1":
            ones += 1
            if ones == STUFF_AFTER:
                stuffed.append("0")   # transparency stuff
                ones = 0
        else:
            ones = 0
    return HDLC_FLAG + "".join(stuffed) + HDLC_FLAG


def hdlc_unstuff(framed_bits: str) -> str:
    """Remove HDLC flags and destuff the 0 that follows five consecutive 1s."""
    if not (framed_bits.startswith(HDLC_FLAG) and framed_bits.endswith(HDLC_FLAG)):
        raise ValueError("bit stream must start and end with the HDLC flag")
    body = framed_bits[len(HDLC_FLAG):len(framed_bits) - len(HDLC_FLAG)]
    out = []
    ones = 0
    i = 0
    while i < len(body):
        bit = body[i]
        out.append(bit)
        if bit == "1":
            ones += 1
            if ones == STUFF_AFTER:
                i += 1  # skip the stuffed 0 that must follow
                ones = 0
        else:
            ones = 0
        i += 1
    return "".join(out)


def bytes_to_bits(data: bytes) -> str:
    """Render bytes as an MSB-first bit string."""
    return "".join(f"{b:08b}" for b in data)


# =============================================================================
# Demonstration helpers
# =============================================================================
def hexline(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def demo_ppp() -> None:
    print("=" * 68)
    print("PPP BYTE STUFFING  (flag=0x7E, escape=0x7D, transform XOR 0x20)")
    print("=" * 68)
    cases = {
        "ordinary text": b"OK",
        "contains a flag 0x7E": bytes([0x7E]),
        "contains an escape 0x7D": bytes([0x7D]),
        "flag + control + escape": bytes([0x7E, 0x11, 0x7D, 0x41]),
        "all flags (worst case)": bytes([0x7E] * 6),
    }
    for label, payload in cases.items():
        framed = ppp_stuff(payload)
        recovered = ppp_unstuff(framed)
        assert recovered == payload, "round trip failed!"
        grew = (len(framed) - 2) / max(len(payload), 1)
        print(f"\n{label}")
        print(f"  payload  : {hexline(payload)}")
        print(f"  on wire  : {hexline(framed)}")
        print(f"  body grew: {grew:.2f}x  (round-trip OK)")


def demo_hdlc() -> None:
    print("\n" + "=" * 68)
    print("HDLC BIT STUFFING  (flag=01111110, stuff 0 after five 1s)")
    print("=" * 68)
    cases = {
        "no long runs": "0110100100",
        "the flag pattern in data": "01111110",
        "long run of ones": "0110" + "1" * 15 + "0010",
        "all ones (worst case)": "1" * 24,
    }
    for label, bits in cases.items():
        framed = hdlc_stuff(bits)
        recovered = hdlc_unstuff(framed)
        assert recovered == bits, "round trip failed!"
        stuffed_count = len(framed) - len(bits) - 2 * len(HDLC_FLAG)
        overhead = 100.0 * stuffed_count / len(bits)
        body = framed[len(HDLC_FLAG):-len(HDLC_FLAG)]
        assert HDLC_FLAG not in body, "flag leaked into data body!"
        print(f"\n{label}")
        print(f"  data   : {bits}")
        print(f"  on wire: {framed}")
        print(f"  stuffed: {stuffed_count} bit(s) -> {overhead:.1f}% overhead "
              f"(flag absent in body: OK)")


def demo_overhead_bound() -> None:
    print("\n" + "=" * 68)
    print("WORST-CASE OVERHEAD CHECK")
    print("=" * 68)
    all_ones = "1" * 800
    framed = hdlc_stuff(all_ones)
    stuffed = len(framed) - len(all_ones) - 2 * len(HDLC_FLAG)
    print(f"  HDLC, 800 all-ones bits -> {stuffed} stuffed "
          f"({100.0 * stuffed / 800:.1f}%, textbook ~12.5%)")
    all_flags = bytes([0x7E] * 400)
    framed_b = ppp_stuff(all_flags)
    ratio = (len(framed_b) - 2) / len(all_flags)
    print(f"  PPP, 400 all-flag bytes -> body x{ratio:.2f} (textbook ~2x)")


def main() -> None:
    demo_ppp()
    demo_hdlc()
    demo_overhead_bound()
    print("\nAll round-trip assertions passed. Framing is transparent.")


if __name__ == "__main__":
    main()
