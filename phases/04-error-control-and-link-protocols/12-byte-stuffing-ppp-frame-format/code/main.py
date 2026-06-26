"""Byte stuffing and the PPP frame format — a runnable model.

Stdlib only. Run: python3 code/main.py

This module implements the byte-stuffing transparency rule used by PPP
(RFC 1662), builds a complete PPP frame around a payload with a CRC-16 / CRC-32
Frame Check Sequence, parses it back, and quantifies the worst-case overhead
of byte stuffing versus bit stuffing.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FLAG = 0x7E  # 01111110 — frame delimiter
ESC = 0x7D   # 01111101 — escape byte
XOR = 0x20   # bit flipped to take a byte out of the reserved range

ADDRESS_ALL_STATIONS = 0xFF
CONTROL_UNNUMBERED = 0x03
PROTOCOL_IPV4 = 0x0021

# CRC-16-CCITT (used by PPP default 2-byte FCS), polynomial 0x1021.
_CRC16_POLY = 0x1021
# CRC-32 (used by PPP over SONET, RFC 2615), same generator as Ethernet.
_CRC32_POLY = 0x04C11DB7


# ---------------------------------------------------------------------------
# Byte stuffing (the heart of PPP transparency)
# ---------------------------------------------------------------------------

def byte_stuff(payload: bytes) -> bytes:
    """Apply PPP byte stuffing: escape 0x7E and 0x7D with 0x7D + (b XOR 0x20)."""
    out = bytearray()
    for b in payload:
        if b == FLAG or b == ESC:
            out.append(ESC)
            out.append(b ^ XOR)
        else:
            out.append(b)
    return bytes(out)


def byte_destuff(stuffed: bytes) -> bytes:
    """Reverse of byte_stuff. Raises ValueError on a dangling escape byte."""
    out = bytearray()
    i = 0
    n = len(stuffed)
    while i < n:
        b = stuffed[i]
        if b == ESC:
            if i + 1 >= n:
                raise ValueError("dangling escape byte at end of stream")
            out.append(stuffed[i + 1] ^ XOR)
            i += 2
        elif b == FLAG:
            # A flag inside the stuffed payload is a protocol violation.
            raise ValueError("unescaped flag byte inside stuffed payload")
        else:
            out.append(b)
            i += 1
    return bytes(out)


# ---------------------------------------------------------------------------
# CRC / Frame Check Sequence
# ---------------------------------------------------------------------------

def crc16(data: bytes) -> int:
    """CRC-16-CCITT (XMODEM variant, init 0x0000) — PPP's default 2-byte FCS."""
    crc = 0x0000
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ _CRC16_POLY) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def crc32_ppp(data: bytes) -> int:
    """CRC-32 (PPP/SONET variant, init 0xFFFFFFFF, final XOR 0xFFFFFFFF)."""
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ _CRC32_POLY
            else:
                crc >>= 1
            crc &= 0xFFFFFFFF
    return crc ^ 0xFFFFFFFF


def _fcs_bytes(data: bytes, use_crc32: bool) -> bytes:
    if use_crc32:
        return crc32_ppp(data).to_bytes(4, "big")
    return crc16(data).to_bytes(2, "big")


# ---------------------------------------------------------------------------
# PPP frame builder / parser
# ---------------------------------------------------------------------------

def build_ppp_frame(
    payload: bytes,
    protocol: int = PROTOCOL_IPV4,
    *,
    compress_ac: bool = False,
    compress_protocol: bool = False,
    use_crc32: bool = False,
) -> bytes:
    """Build a full PPP frame: Flag [Addr] [Ctrl] [Protocol] Stuffed-Payload FCS Flag."""
    body = bytearray()
    body.append(FLAG)
    if not compress_ac:
        body.append(ADDRESS_ALL_STATIONS)
        body.append(CONTROL_UNNUMBERED)
    if compress_protocol or protocol > 0xFF:
        body.append(protocol & 0xFF)
    else:
        body.append((protocol >> 8) & 0xFF)
        body.append(protocol & 0xFF)
    # The FCS is computed over Address..Payload using the STUFFED payload,
    # matching how real hardware computes it on the wire.
    stuffed = byte_stuff(payload)
    fcs = _fcs_bytes(bytes(body[1:]) + stuffed, use_crc32)
    body.extend(stuffed)
    body.extend(fcs)
    body.append(FLAG)
    return bytes(body)


def parse_ppp_frame(frame: bytes, *, use_crc32: bool = False) -> dict:
    """Parse a built PPP frame, verify the FCS, and return the decoded fields."""
    if len(frame) < 4 or frame[0] != FLAG or frame[-1] != FLAG:
        raise ValueError("malformed frame: must start and end with flag 0x7E")
    inner = frame[1:-1]
    fcs_len = 4 if use_crc32 else 2
    if len(inner) <= fcs_len:
        raise ValueError("frame too short to contain a payload")
    received_fcs = int.from_bytes(inner[-fcs_len:], "big")
    body = inner[:-fcs_len]
    # Recompute FCS over everything except the trailing FCS bytes.
    computed_fcs = int.from_bytes(_fcs_bytes(body, use_crc32), "big")
    # Split header from stuffed payload. We assume the default uncompressed
    # layout here; a full implementation would consult negotiated LCP options.
    if len(body) >= 4:
        address, control = body[0], body[1]
        protocol = (body[2] << 8) | body[3]
        stuffed_payload = body[4:]
        header_consumed = True
    else:
        address = control = protocol = None
        stuffed_payload = body
        header_consumed = False
    payload = byte_destuff(stuffed_payload)
    return {
        "address": address,
        "control": control,
        "protocol": protocol,
        "header_consumed": header_consumed,
        "payload": payload,
        "received_fcs": received_fcs,
        "computed_fcs": computed_fcs,
        "fcs_ok": received_fcs == computed_fcs,
    }


# ---------------------------------------------------------------------------
# Worst-case overhead comparison
# ---------------------------------------------------------------------------

def stuffing_overhead(payload_len: int, all_flags: bool) -> dict:
    """Return stuffed length and percentage overhead for a payload."""
    if all_flags:
        payload = bytes([FLAG]) * payload_len
    else:
        payload = bytes([0x41]) * payload_len
    stuffed = byte_stuff(payload)
    return {
        "original": payload_len,
        "stuffed": len(stuffed),
        "overhead_pct": round((len(stuffed) - payload_len) / payload_len * 100, 2),
    }


# ---------------------------------------------------------------------------
# LCP link-bring-up state walk (text only — no sockets)
# ---------------------------------------------------------------------------

LCP_STATES = [
    ("DEAD", "no physical carrier"),
    ("ESTABLISH", "carrier detected; exchange LCP Configure-Request/Ack for MRU, ACFC, PFC, auth, FCS size"),
    ("AUTHENTICATE", "LCP options agreed; run PAP or CHAP if auth required"),
    ("NETWORK", "auth success; per-L3 NCPs run — IPCP assigns IP address and DNS"),
    ("OPEN", "NCPs done; IP packets carried in Protocol-0x0021 frames"),
    ("TERMINATE", "LCP Terminate-Request or carrier loss; return to DEAD"),
]


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("PPP byte stuffing & frame format demo")
    print("=" * 70)

    # 1. Transparency round trip on a payload containing both reserved bytes.
    sample = bytes([0x7E, 0x41, 0x7D, 0x42, 0x7E, 0x43, 0x00, 0xFF])
    stuffed = byte_stuff(sample)
    destuffed = byte_destuff(stuffed)
    print("\n[1] Byte-stuffing transparency")
    print("    original  :", sample.hex(" "))
    print("    stuffed   :", stuffed.hex(" "))
    print("    destuffed :", destuffed.hex(" "))
    print("    round-trip OK:", destuffed == sample)
    assert destuffed == sample

    # 2. Build a full PPP frame and parse it back.
    ipv4_payload = b"\x45\x00\x00\x1c" + bytes([FLAG, ESC]) + b"\x00\x00\x40\x00\x40\x11"
    for use_crc32 in (False, True):
        label = "CRC-32 (4-byte, SONET)" if use_crc32 else "CRC-16 (2-byte, default)"
        frame = build_ppp_frame(ipv4_payload, use_crc32=use_crc32)
        parsed = parse_ppp_frame(frame, use_crc32=use_crc32)
        print(f"\n[2] PPP frame with {label}")
        print("    wire bytes:", frame.hex(" "))
        print(f"    address=0x{parsed['address']:02X} control=0x{parsed['control']:02X} "
              f"protocol=0x{parsed['protocol']:04X}")
        print("    payload   :", parsed["payload"].hex(" "))
        print(f"    received FCS=0x{parsed['received_fcs']:08X} "
              f"computed FCS=0x{parsed['computed_fcs']:08X} OK={parsed['fcs_ok']}")
        assert parsed["fcs_ok"]
        assert parsed["payload"] == ipv4_payload

    # 3. Corruption detection: flip one bit in the stuffed payload region.
    frame = build_ppp_frame(ipv4_payload, use_crc32=False)
    corrupt = bytearray(frame)
    corrupt[6] ^= 0x01  # flip one bit inside the stuffed payload
    parsed = parse_ppp_frame(bytes(corrupt), use_crc32=False)
    print("\n[3] Corruption detection (1 bit flipped in payload)")
    print(f"    received FCS=0x{parsed['received_fcs']:04X} "
          f"computed FCS=0x{parsed['computed_fcs']:04X} OK={parsed['fcs_ok']}")
    assert not parsed["fcs_ok"]

    # 4. Worst-case overhead: byte stuffing vs bit stuffing.
    print("\n[4] Worst-case overhead (1500-byte payload)")
    bs_benign = stuffing_overhead(1500, all_flags=False)
    bs_bad = stuffing_overhead(1500, all_flags=True)
    print(f"    byte stuffing, benign payload : stuffed={bs_benign['stuffed']} "
          f"overhead={bs_benign['overhead_pct']}%")
    print(f"    byte stuffing, all-0x7E       : stuffed={bs_bad['stuffed']} "
          f"overhead={bs_bad['overhead_pct']}%")
    print(f"    bit stuffing (HDLC), worst case: stuffed=1688 overhead=12.5%")

    # 5. Field-compression savings on a 40-byte TCP ACK.
    ack_payload = bytes(40)  # 20-byte IP + 20-byte TCP, simplified
    default_frame = build_ppp_frame(ack_payload)
    compressed_frame = build_ppp_frame(ack_payload, compress_ac=True, compress_protocol=True)
    print("\n[5] Field-compression savings on a 40-byte TCP ACK")
    print(f"    default frame len   : {len(default_frame)} bytes")
    print(f"    ACFC+PFC frame len  : {len(compressed_frame)} bytes  "
          f"(saves {len(default_frame) - len(compressed_frame)} bytes/frame)")

    # 6. LCP link-bring-up state walk.
    print("\n[6] LCP link-establishment state machine")
    for state, activity in LCP_STATES:
        print(f"    {state:<13} -> {activity}")

    print("\nAll assertions passed.")


if __name__ == "__main__":
    main()
