"""Error-detecting codes and a Utopian simplex protocol — a worked toolkit.

This stdlib-only module makes the three error-detecting codes from the data
link layer concrete, then drives a tiny "Utopia" (Protocol 1) simulation so you
can see why an error-free channel lets the sender drop every checksum.

What it implements:

  * even_parity_bit / vrc_lrc_block  -- single parity bit and the 2-D
    (row + column) parity block that survives k-bit and short burst errors.
  * internet_checksum                -- the 16-bit one's-complement checksum
    used by IPv4/UDP/TCP (RFC 1071), including the end-around carry fold.
  * crc_remainder / crc_frame        -- modulo-2 polynomial long division,
    matching Tanenbaum's Fig. 3-9 worked example (G = x^4 + x + 1) and the
    IEEE 802.3 / Ethernet CRC-32 generator (0x04C11DB7).
  * UtopiaChannel + sender1/receiver1 -- Protocol 1: simplex, no sequence
    numbers, no ACKs, no flow control, an error-free channel.

Run:  python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Tuple

# Tanenbaum Fig. 3-9 generator: x^4 + x + 1  ->  bits 1 0 0 1 1  (degree 4)
CRC_GEN_X4_X_1 = 0b10011
# IEEE 802.3 / Ethernet CRC-32 generator polynomial (x^32 ... +1, normal form).
IEEE_802_3_CRC32_GEN = 0x104C11DB7


# --------------------------------------------------------------------------- #
# 1. Parity: single bit (VRC) and 2-D row/column block (VRC + LRC)
# --------------------------------------------------------------------------- #
def even_parity_bit(data_bits: Iterable[int]) -> int:
    """Return the even parity bit: the XOR (mod-2 sum) of all data bits."""
    parity = 0
    for bit in data_bits:
        parity ^= bit & 1
    return parity


def vrc_lrc_block(rows: List[List[int]]) -> Tuple[List[int], List[int]]:
    """Compute per-row parity (VRC) and per-column parity (LRC) for a block.

    A 2-D parity block reliably detects every error of up to k bits and any
    single burst whose length is <= the number of rows: a burst hits a
    different column in each row, so the column parity flags it (Fig. 3-8).
    """
    if not rows:
        return [], []
    width = len(rows[0])
    row_parity = [even_parity_bit(r) for r in rows]
    col_parity = [
        even_parity_bit(rows[r][c] for r in range(len(rows)))
        for c in range(width)
    ]
    return row_parity, col_parity


# --------------------------------------------------------------------------- #
# 2. Internet checksum (RFC 1071): 16-bit one's-complement sum
# --------------------------------------------------------------------------- #
def internet_checksum(data: bytes) -> int:
    """Compute the 16-bit one's-complement Internet checksum (RFC 1071).

    Pads an odd final byte with a zero byte, folds every carry above bit 15
    back into the low bits (end-around carry), then returns the one's
    complement. Summing a frame *including* a correct checksum yields 0x0000.
    """
    if len(data) % 2:
        data = data + b"\x00"
    total = 0
    for i in range(0, len(data), 2):
        total += (data[i] << 8) | data[i + 1]
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def verify_internet_checksum(data: bytes, checksum: int) -> bool:
    """Frame is intact when sum(data)+checksum folds to 0xFFFF, so ~ == 0."""
    return internet_checksum(data + checksum.to_bytes(2, "big")) == 0


# --------------------------------------------------------------------------- #
# 3. CRC: modulo-2 polynomial long division
# --------------------------------------------------------------------------- #
def crc_remainder(message_bits: int, generator: int) -> int:
    """Return the modulo-2 remainder of message_bits divided by generator.

    Modulo-2 division uses XOR for subtraction (no carries/borrows). The
    divisor "goes into" the dividend whenever the dividend has as many bits.
    """
    gen_len = generator.bit_length()
    remainder = message_bits
    while remainder.bit_length() >= gen_len:
        shift = remainder.bit_length() - gen_len
        remainder ^= generator << shift
    return remainder


def crc_frame(message_bits: int, generator: int) -> Tuple[int, int]:
    """Append r zero bits, divide, subtract the remainder. Returns (frame, crc).

    The transmitted polynomial T(x) is then exactly divisible by G(x), so the
    receiver's division yields a zero remainder for an undamaged frame.
    """
    r = generator.bit_length() - 1
    shifted = message_bits << r          # x^r * M(x): append r zero bits
    crc = crc_remainder(shifted, generator)
    return shifted ^ crc, crc            # subtract remainder (XOR)


# --------------------------------------------------------------------------- #
# 4. Protocol 1: A Utopian Simplex Protocol (error-free, simplex, no control)
# --------------------------------------------------------------------------- #
@dataclass
class Frame:
    """Utopia only fills info; seq/ack fields exist but are unused here."""
    info: bytes
    seq: int = 0   # MAX_SEQ not needed in Utopia
    ack: int = 0


@dataclass
class UtopiaChannel:
    """A perfect channel: never damages, never loses, never reorders frames."""
    wire: List[Frame] = field(default_factory=list)

    def to_physical_layer(self, frame: Frame) -> None:
        self.wire.append(frame)

    def from_physical_layer(self) -> Frame:
        return self.wire.pop(0)

    def has_frame(self) -> bool:
        return bool(self.wire)


def sender1(channel: UtopiaChannel, packets: List[bytes]) -> None:
    """Pump packets onto the line as fast as possible; no ACK is awaited."""
    for buffer in packets:                 # from_network_layer(&buffer)
        s = Frame(info=buffer)             # s.info = buffer
        channel.to_physical_layer(s)       # to_physical_layer(&s)


def receiver1(channel: UtopiaChannel) -> List[bytes]:
    """Wait for frame_arrival, lift it off the wire, hand info to net layer."""
    delivered: List[bytes] = []
    while channel.has_frame():             # wait_for_event -> frame_arrival
        r = channel.from_physical_layer()  # from_physical_layer(&r)
        delivered.append(r.info)           # to_network_layer(&r.info)
    return delivered


# --------------------------------------------------------------------------- #
# Demonstration
# --------------------------------------------------------------------------- #
def _fmt_bits(value: int, width: int) -> str:
    return format(value, f"0{width}b")


def main() -> None:
    print("=" * 68)
    print("1. PARITY")
    print("=" * 68)
    data = [1, 0, 1, 1, 0, 1, 0]
    p = even_parity_bit(data)
    print(f"data 1011010  even-parity bit = {p}  -> codeword 1011010{p}")
    print("(distance-2 code: detects all single-bit errors, corrects none)\n")

    block = [[1, 0, 1, 1, 0, 0, 1],
             [0, 1, 1, 0, 1, 0, 1],
             [1, 1, 0, 0, 0, 1, 0]]
    row_p, col_p = vrc_lrc_block(block)
    print("2-D parity block (3 rows x 7 cols):")
    for r, rp in zip(block, row_p):
        print("   " + " ".join(map(str, r)) + f"  | row parity {rp}")
    print("   " + " ".join(map(str, col_p)) + "  <- column parity (LRC)\n")

    print("=" * 68)
    print("2. INTERNET CHECKSUM (RFC 1071, 16-bit one's complement)")
    print("=" * 68)
    payload = b"\x45\x00\x00\x3c\x1c\x46\x40\x00\x40\x06"
    cks = internet_checksum(payload)
    print(f"payload bytes : {payload.hex()}")
    print(f"checksum      : 0x{cks:04x}")
    print(f"verify intact : {verify_internet_checksum(payload, cks)}")
    corrupted = bytearray(payload)
    corrupted[4] ^= 0x01  # flip one bit
    print(f"verify flipped: {verify_internet_checksum(bytes(corrupted), cks)} "
          "(single bit flip detected)\n")

    print("=" * 68)
    print("3. CRC  (Tanenbaum Fig. 3-9: frame 1101011111, G = x^4 + x + 1)")
    print("=" * 68)
    msg = 0b1101011111
    frame, crc = crc_frame(msg, CRC_GEN_X4_X_1)
    print(f"message     : {_fmt_bits(msg, 10)}")
    print(f"CRC (4 bits): {_fmt_bits(crc, 4)}")
    print(f"transmitted : {_fmt_bits(frame, 14)}")
    print(f"recv divide : remainder = {crc_remainder(frame, CRC_GEN_X4_X_1)} (0 = OK)")
    flipped = frame ^ (1 << 7)
    print(f"1-bit error : remainder = {crc_remainder(flipped, CRC_GEN_X4_X_1)} "
          "(non-zero -> caught)")
    crc32 = crc_remainder(0xDEADBEEF << 32, IEEE_802_3_CRC32_GEN)
    print(f"\nIEEE 802.3 CRC-32 of 0xDEADBEEF (raw, unreflected): 0x{crc32:08X}\n")

    print("=" * 68)
    print("4. PROTOCOL 1 — A UTOPIAN SIMPLEX PROTOCOL")
    print("=" * 68)
    channel = UtopiaChannel()
    packets = [b"frame-A", b"frame-B", b"frame-C"]
    sender1(channel, packets)
    print(f"sender pumped {len(packets)} frames; no ACK awaited, no seq numbers")
    delivered = receiver1(channel)
    for info in delivered:
        print(f"   receiver delivered to network layer: {info!r}")
    assert delivered == packets, "Utopia must deliver every frame, in order"
    print("error-free channel => no checksum field is even consulted.")


if __name__ == "__main__":
    main()
