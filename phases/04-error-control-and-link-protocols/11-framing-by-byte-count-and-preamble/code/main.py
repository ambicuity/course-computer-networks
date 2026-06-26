"""Byte-count and preamble-plus-length framing.

Demonstrates the four classic data-link framing strategies from Tanenbaum et al.,
Computer Networks (Sec. 3.1.2), with a focus on (1) pure byte-count framing and
its fatal count-garbling failure mode, and (2) the preamble-plus-length hybrid
used by real LANs such as Ethernet (IEEE 802.3) and 802.11.

Stdlib only. No network calls. Run: python3 main.py
"""

from __future__ import annotations

import binascii
import zlib

# --- Constants ------------------------------------------------------------

PPP_FLAG = 0x7E
PPP_ESCAPE = 0x7D
PPP_XOR = 0x20  # PPP stuffs by XORing the byte with 0x20 (RFC 1662)

ETHER_PREAMBLE = bytes([0x55] * 7)
ETHER_SFD = bytes([0xD5])
ETHER_TYPE_IPV4 = 0x0800
ETHER_LENGTH_MAX = 1500  # values <= 1500 mean Length; >= 1536 mean EtherType


# --- Method 1: Byte count -------------------------------------------------

def byte_count_frame(payload: bytes) -> bytes:
    """Frame payload with a single leading byte giving total frame length.

    The count covers itself plus the payload (matches the textbook's Fig. 3-3
    where a count of 5 precedes 4 payload bytes).
    """
    if len(payload) > 254:
        raise ValueError("byte_count_frame: payload too large for 1-byte count")
    count = len(payload) + 1
    return bytes([count]) + payload


def byte_count_parse(stream: bytes, max_frames: int = 8) -> list[bytes]:
    """Parse a byte-count stream back into frames.

    Returns a list of payloads. If a length field is corrupt the parser walks
    the stream at the wrong offset and produces garbage -- the point of the demo.
    """
    frames: list[bytes] = []
    i = 0
    while i < len(stream) and len(frames) < max_frames:
        count = stream[i]
        if count == 0 or i + count > len(stream):
            # Ran off the end (or a zero count) -- desynchronized.
            break
        payload = stream[i + 1 : i + count]
        frames.append(payload)
        i += count
    return frames


def inject_bit_flip(frame: bytes, byte_index: int, bit_index: int) -> bytes:
    """Flip a single bit at the given byte/bit position (big-endian bit order)."""
    b = bytearray(frame)
    b[byte_index] ^= 1 << (7 - bit_index)
    return bytes(b)


# --- Method 2: PPP flag bytes with byte stuffing (RFC 1662) ---------------

def ppp_frame(payload: bytes, include_fcs: bool = True) -> bytes:
    """Frame payload between PPP flag bytes, byte-stuffing 0x7E and 0x7D."""
    stuffed = bytearray()
    for b in payload:
        if b == PPP_FLAG or b == PPP_ESCAPE:
            stuffed.append(PPP_ESCAPE)
            stuffed.append(b ^ PPP_XOR)
        else:
            stuffed.append(b)
    body = bytes(stuffed)
    if include_fcs:
        fcs = zlib.crc32(body) & 0xFFFFFFFF  # stand-in for the PPP 16/32-bit FCS
        body += fcs.to_bytes(4, "big")
    return bytes([PPP_FLAG]) + body + bytes([PPP_FLAG])


def ppp_parse(frame: bytes) -> bytes:
    """Reverse PPP framing: strip flags and destuff."""
    if len(frame) < 2 or frame[0] != PPP_FLAG or frame[-1] != PPP_FLAG:
        raise ValueError("ppp_parse: missing flag delimiters")
    body = frame[1:-1]
    out = bytearray()
    i = 0
    while i < len(body):
        b = body[i]
        if b == PPP_ESCAPE:
            i += 1
            if i >= len(body):
                raise ValueError("ppp_parse: dangling escape")
            out.append(body[i] ^ PPP_XOR)
        elif b == PPP_FLAG:
            raise ValueError("ppp_parse: unexpected flag inside frame")
        else:
            out.append(b)
        i += 1
    # Last 4 bytes are the FCS stand-in; return payload only.
    return bytes(out[:-4]) if len(out) >= 4 else bytes(out)


# --- Method 3: Preamble + length (Ethernet 802.3) -------------------------

def ethernet_frame(payload: bytes, dst: bytes = b"\xff" * 6, src: bytes = b"\x00" * 6) -> bytes:
    """Build an 802.3-style frame: preamble, SFD, addrs, Length, payload, FCS.

    The Length field is the byte count of the payload only. The FCS is a real
    CRC-32 (same polynomial family Ethernet uses) over DA+SA+Length+Payload.
    """
    if len(payload) < 46:
        payload = payload + b"\x00" * (46 - len(payload))  # minimum payload
    if len(payload) > ETHER_LENGTH_MAX:
        raise ValueError("ethernet_frame: payload exceeds MTU")
    length = len(payload).to_bytes(2, "big")
    body = dst + src + length + payload
    fcs = (binascii.crc32(body) & 0xFFFFFFFF).to_bytes(4, "big")
    return ETHER_PREAMBLE + ETHER_SFD + body + fcs


def ethernet_parse(frame: bytes) -> dict:
    """Parse an Ethernet frame, returning the delimiting fields and payload."""
    if frame[:7] != ETHER_PREAMBLE:
        raise ValueError("ethernet_parse: bad preamble")
    if frame[7:8] != ETHER_SFD:
        raise ValueError("ethernet_parse: bad SFD")
    body = frame[8:]
    dst, src = body[0:6], body[6:12]
    field = int.from_bytes(body[12:14], "big")
    if field <= ETHER_LENGTH_MAX:
        length, ethertype = field, None
        payload = body[14 : 14 + length]
    else:
        length, ethertype = None, field
        # Ethernet II: payload runs to just before the 4-byte FCS.
        payload = body[14:-4]
    fcs = body[-4:]
    return {
        "dst": dst.hex(":"),
        "src": src.hex(":"),
        "length": length,
        "ethertype": hex(ethertype) if ethertype else None,
        "payload": payload,
        "fcs_ok": (binascii.crc32(body[:-4]) & 0xFFFFFFFF) == int.from_bytes(fcs, "big"),
    }


# --- Demo -----------------------------------------------------------------

def _hex(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def main() -> None:
    payload = bytes([0x03, 0x7E, 0x7D, 0xFF, 0x00])
    print("Payload:        ", _hex(payload))
    print("=" * 72)

    # 1. Byte count -- clean
    f1 = byte_count_frame(payload)
    print("Byte-count frame:", _hex(f1))
    print("Parsed back:     ", _hex(byte_count_parse(f1)[0]))
    print()

    # 2. Byte count -- with a single bit flip in the first length field.
    #    A two-frame stream shows the desync eating into frame 2.
    f2 = byte_count_frame(bytes([0x41, 0x42, 0x43]))  # frame 2: 04 41 42 43
    stream = f1 + f2
    corrupt = bytearray(stream)
    corrupt[0] = f1[0] ^ 0x01  # 0x06 -> 0x07: count grows by one
    corrupt = bytes(corrupt)
    print("Clean stream:    ", _hex(stream))
    print("Corrupted stream:", _hex(corrupt), "(frame-1 length 06 -> 07)")
    parsed = byte_count_parse(corrupt)
    print("Parsed frames:   ", [_hex(p) for p in parsed])
    print(">>> Frame 1 now claims 7 bytes, so the parser consumes one byte of")
    print("    frame 2's length field. Frame 2 is then read at the wrong offset")
    print("    and the receiver never recovers the true boundary. This is why")
    print("    byte count is never used alone.")
    print()

    # 3. PPP with byte stuffing
    pf = ppp_frame(payload)
    print("PPP frame:       ", _hex(pf))
    print("PPP parsed back: ", _hex(ppp_parse(pf)))
    print(f"Wire overhead:   {len(pf)} bytes for {len(payload)} payload bytes "
          f"(flags + stuffing + 4-byte FCS stand-in)")
    print()

    # 4. Ethernet preamble + length
    ef = ethernet_frame(payload)
    print("Ethernet frame:  ", _hex(ef))
    info = ethernet_parse(ef)
    print("  dst            ", info["dst"])
    print("  src            ", info["src"])
    print("  length         ", info["length"])
    print("  ethertype      ", info["ethertype"])
    print("  payload        ", _hex(info["payload"].rstrip(b"\x00")))
    print("  fcs_ok         ", info["fcs_ok"])
    print()

    # 5. EtherType (Ethernet II) detection
    eth2 = (ETHER_PREAMBLE + ETHER_SFD + b"\xff" * 6 + b"\x00" * 6
            + ETHER_TYPE_IPV4.to_bytes(2, "big") + payload + b"\x00" * 4)
    field_val = int.from_bytes(eth2[8 + 12 : 8 + 14], "big")
    print("Ethernet II (Type=0x0800 IPv4):")
    print("  field value    ", field_val)
    print("  interpretation ", "EtherType (>=1536)" if field_val >= 1536 else "Length (<=1500)")
    print()

    # 6. Worked comparison table
    print("Scheme          | wire bytes | notes")
    print("----------------+------------+-------------------------------")
    print(f"byte-count      | {len(byte_count_frame(payload)):>10} | 1-byte count, no recovery")
    print(f"PPP stuffed     | {len(ppp_frame(payload)):>10} | flags + escape on 0x7E/0x7D")
    print(f"Ethernet        | {len(ethernet_frame(payload)):>10} | preamble+SFD+length+CRC-32")


if __name__ == "__main__":
    main()
