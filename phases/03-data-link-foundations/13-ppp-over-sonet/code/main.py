"""PPP over SONET (Packet over SONET / POS) framing, CRC-32, byte-stuffing, and a
tiny LCP option-negotiation simulator.

Pure stdlib, no network access. Run: python3 main.py

This module models the on-wire bytes of a PPP frame as carried over a SONET
synchronous payload envelope per RFC 2615, using the HDLC-like framing of
RFC 1662: a 0x7E flag, fixed Address (0xFF) and Control (0x03) fields, a
2-byte Protocol field, the payload, and a 4-byte CRC-32 FCS (mandatory on
SONET). It also implements the byte-stuffing escape rule and a minimal LCP
Configure-Request/Ack exchange.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Constants (RFC 1662 framing; RFC 2615 mandates CRC-32 over SONET)
# ---------------------------------------------------------------------------
FLAG = 0x7E
ESCAPE = 0x7D
ADDRESS = 0xFF
CONTROL = 0x03
XOR_VALUE = 0x20

# Common Protocol field values (RFC 1661 / assigned numbers)
PROTO_IPV4 = 0x0021
PROTO_IPV6 = 0x0057
PROTO_LCP = 0xC021
PROTO_IPCP = 0x8021

# LCP packet codes (RFC 1661 sec. 6)
LCP_CONFIGURE_REQUEST = 1
LCP_CONFIGURE_ACK = 2
LCP_CONFIGURE_NAK = 3
LCP_CONFIGURE_REJECT = 4
LCP_TERMINATE_REQUEST = 5
LCP_TERMINATE_ACK = 6

# LCP option types we model
OPT_MRU = 1
OPT_AUTH_PROTOCOL = 3
OPT_MAGIC_NUMBER = 5
OPT_PFC = 7
OPT_ACFC = 8


# ---------------------------------------------------------------------------
# Byte stuffing (RFC 1662 sec. 5)
# ---------------------------------------------------------------------------
def stuff(data: bytes) -> bytes:
    """Apply PPP byte-stuffing: escape 0x7E, 0x7D, and any byte < 0x20."""
    out = bytearray()
    for b in data:
        if b == FLAG or b == ESCAPE or b < 0x20:
            out.append(ESCAPE)
            out.append(b ^ XOR_VALUE)
        else:
            out.append(b)
    return bytes(out)


def unstuff(data: bytes) -> bytes:
    """Reverse byte-stuffing: on 0x7D, drop it and XOR next byte with 0x20."""
    out = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b == ESCAPE:
            if i + 1 >= len(data):
                raise ValueError("dangling escape byte at end of stream")
            out.append(data[i + 1] ^ XOR_VALUE)
            i += 2
        else:
            out.append(b)
            i += 1
    return bytes(out)


# ---------------------------------------------------------------------------
# CRC-32 FCS (RFC 1662; same polynomial 0x04C11DB7 as Ethernet/AAL5)
# ---------------------------------------------------------------------------
_CRC32_TABLE: list[int] | None = None


def _build_crc32_table() -> list[int]:
    table = []
    for n in range(256):
        crc = n << 24
        for _ in range(8):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
        table.append(crc)
    return table


def crc32_ppp(data: bytes) -> int:
    """Compute the PPP CRC-32 FCS (MSB-first, complemented) over `data`."""
    global _CRC32_TABLE
    if _CRC32_TABLE is None:
        _CRC32_TABLE = _build_crc32_table()
    crc = 0xFFFFFFFF
    for b in data:
        crc = ((crc << 8) ^ _CRC32_TABLE[((crc >> 24) ^ b) & 0xFF]) & 0xFFFFFFFF
    return crc ^ 0xFFFFFFFF


def fcs32_bytes(data: bytes) -> bytes:
    """Return the 4-byte FCS, transmitted most-significant byte first."""
    fcs = crc32_ppp(data)
    return bytes([(fcs >> 24) & 0xFF, (fcs >> 16) & 0xFF,
                  (fcs >> 8) & 0xFF, fcs & 0xFF])


def _crc16_bytes(data: bytes) -> bytes:
    """CRC-16 FCS (industry-standard, reflected 0x8408) - low-speed PPP only."""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
            crc &= 0xFFFF
    crc ^= 0xFFFF
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])


# ---------------------------------------------------------------------------
# Frame build / parse
# ---------------------------------------------------------------------------
def build_frame(protocol: int, payload: bytes,
                compress_acfc: bool = False, compress_pfc: bool = False,
                use_crc32: bool = True) -> bytes:
    """Build a complete stuffed PPP frame between two 0x7E flags.

    The FCS is computed over the UNSTUFFED body (Address..Payload), then the
    FCS itself is stuffed along with the body before the flags are added.
    """
    body = bytearray()
    if not compress_acfc:
        body.append(ADDRESS)
        body.append(CONTROL)
    if compress_pfc and protocol <= 0xFF:
        body.append(protocol & 0xFF)
    else:
        body.append((protocol >> 8) & 0xFF)
        body.append(protocol & 0xFF)
    body.extend(payload)
    fcs = fcs32_bytes(bytes(body)) if use_crc32 else _crc16_bytes(bytes(body))
    body.extend(fcs)
    stuffed = stuff(bytes(body))
    return bytes([FLAG]) + stuffed + bytes([FLAG])


def parse_frame(frame: bytes) -> dict:
    """Parse a single PPP frame, verify the FCS, return decoded fields.

    Raises ValueError on bad flag, bad escape, or FCS mismatch.
    """
    if len(frame) < 6 or frame[0] != FLAG or frame[-1] != FLAG:
        raise ValueError("malformed frame: missing leading/trailing flag")
    stuffed_body = frame[1:-1]
    body = unstuff(stuffed_body)
    if len(body) < 4:
        raise ValueError("frame body too short for FCS")
    fcs_received = body[-4:]
    body_without_fcs = body[:-4]

    fcs_computed = fcs32_bytes(body_without_fcs)
    if fcs_computed != fcs_received:
        raise ValueError(
            f"FCS mismatch: got {fcs_received.hex()} expected {fcs_computed.hex()}"
        )

    idx = 0
    address = control = None
    if body_without_fcs[idx] == ADDRESS:
        address = body_without_fcs[idx]
        control = body_without_fcs[idx + 1]
        idx += 2
    # Protocol: 1 byte if low bit of first byte is 1 (PFC), else 2 bytes.
    if body_without_fcs[idx] & 0x01:
        protocol = body_without_fcs[idx]
        idx += 1
    else:
        protocol = (body_without_fcs[idx] << 8) | body_without_fcs[idx + 1]
        idx += 2
    payload = body_without_fcs[idx:]
    return {
        "address": address,
        "control": control,
        "protocol": protocol,
        "payload": payload,
        "fcs": fcs_received,
    }


# ---------------------------------------------------------------------------
# SONET scrambler (x^7+x^6+1, self-synchronous) - illustrative
# ---------------------------------------------------------------------------
def sonet_scramble(data: bytes, seed: int = 0x7F) -> bytes:
    """Self-synchronous scrambler for the x^7+x^6+1 polynomial (ITU-T G.707).

    Illustrates the scrambling step mandated by RFC 2615 to guarantee bit
    transitions for SONET clock recovery.
    """
    state = seed & 0x7F
    out = bytearray()
    for b in data:
        feedback = ((state >> 6) ^ (state >> 5)) & 0x01
        key = ((state >> 6) ^ (state >> 5)) & 0xFF
        out.append(b ^ key)
        state = ((state << 1) | feedback) & 0x7F
    return bytes(out)


def sonet_descramble(data: bytes, seed: int = 0x7F) -> bytes:
    """Descramble is identical to scramble for a self-synchronous design."""
    return sonet_scramble(data, seed)


# ---------------------------------------------------------------------------
# LCP option negotiation (mini-simulator)
# ---------------------------------------------------------------------------
def lcp_packet(code: int, identifier: int, options: bytes) -> bytes:
    """Build an LCP packet carried as a PPP payload (Protocol 0xC021)."""
    length = 4 + len(options)
    return bytes([code, identifier, (length >> 8) & 0xFF, length & 0xFF]) + options


def encode_option(opt_type: int, value: bytes) -> bytes:
    return bytes([opt_type, 2 + len(value)]) + value


def lcp_negotiate(proposed: list[tuple[int, bytes]],
                  peer_supports: set[int],
                  on_pos: bool = True) -> dict:
    """Simulate an LCP Configure-Request and the peer's response.

    On a POS (SONET) link, RFC 2615 recommends rejecting ACFC and PFC even
    if supported, because the byte savings is negligible at OC-48 rates.
    """
    acked: list[tuple[int, bytes]] = []
    rejected: list[int] = []
    for opt_type, value in proposed:
        if opt_type not in peer_supports:
            rejected.append(opt_type)
        elif on_pos and opt_type in (OPT_ACFC, OPT_PFC):
            rejected.append(opt_type)  # RFC 2615: do not compress on SONET
        else:
            acked.append((opt_type, value))
    options_req = b"".join(encode_option(t, v) for t, v in proposed)
    options_ack = b"".join(encode_option(t, v) for t, v in acked)
    resp_code = LCP_CONFIGURE_ACK if not rejected else LCP_CONFIGURE_REJECT
    resp_opts = options_ack if not rejected else b"".join(
        encode_option(t, b"") for t in rejected)
    return {
        "request": lcp_packet(LCP_CONFIGURE_REQUEST, 1, options_req),
        "response_code": resp_code,
        "acked": acked,
        "rejected": rejected,
        "response": lcp_packet(resp_code, 1, resp_opts),
    }


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
def main() -> None:
    print("=== PPP over SONET framing demo (RFC 1661/1662/2615) ===\n")

    # 1. A 20-byte IPv4 header as the payload, including bytes that need stuffing.
    ipv4_header = bytes([
        0x45, 0x00, 0x00, 0x14,        # ver/ihl, tos, total length
        0x00, 0x01, 0x00, 0x00,        # id, flags, frag
        0x40, 0x06, 0x00, 0x00,        # ttl=64, proto=TCP, bad checksum (demo)
        0x7E, 0x00, 0x7D, 0x01,        # src (contains 0x7E, 0x7D, 0x00!)
        0x0A, 0x00, 0x00, 0x01,        # dst
    ])
    print(f"Payload ({len(ipv4_header)} bytes): {ipv4_header.hex()}")
    print("  (note in-payload 0x7E at offset 12, 0x7D at 14, 0x00 at 13)\n")

    frame = build_frame(PROTO_IPV4, ipv4_header, use_crc32=True)
    print(f"POS frame ({len(frame)} bytes, CRC-32, uncompressed):")
    print(f"  {frame.hex()}\n")

    # 2. Round-trip parse.
    parsed = parse_frame(frame)
    print(f"Parsed: protocol=0x{parsed['protocol']:04X} "
          f"addr=0x{parsed['address']:02X} ctrl=0x{parsed['control']:02X}")
    print(f"  payload recovered == original: {parsed['payload'] == ipv4_header}")
    print(f"  FCS-32: {parsed['fcs'].hex()}\n")

    # 3. Overhead comparison.
    big = b"\x41" * 1500
    pos_frame = build_frame(PROTO_IPV4, big, use_crc32=True)
    comp_frame = build_frame(PROTO_IPV4, big,
                             compress_acfc=True, compress_pfc=True,
                             use_crc32=False)
    pos_overhead = (len(pos_frame) - 1500) / 1500 * 100
    comp_overhead = (len(comp_frame) - 1500) / 1500 * 100
    print("Overhead for a 1500-byte packet:")
    print(f"  POS (CRC-32, uncompressed):   {len(pos_frame)} bytes, "
          f"overhead {pos_overhead:.2f}%")
    print(f"  Low-speed (CRC-16, ACFC+PFC): {len(comp_frame)} bytes, "
          f"overhead {comp_overhead:.2f}%\n")

    # 4. Corruption detection.
    corrupted = bytearray(frame)
    corrupted[6] ^= 0x01  # flip a payload bit
    try:
        parse_frame(bytes(corrupted))
    except ValueError as e:
        print(f"Corruption detection: flipped bit -> {e}\n")

    # 5. Scrambling illustration.
    body = frame[1:-1]
    scrambled = sonet_scramble(body)
    restored = sonet_descramble(scrambled)
    print(f"SONET scrambler (x^7+x^6+1): round-trip OK = {restored == body}")
    print(f"  first 8 body bytes:      {body[:8].hex()}")
    print(f"  first 8 scrambled bytes: {scrambled[:8].hex()}\n")

    # 6. LCP negotiation.
    proposed = [
        (OPT_MRU, b"\x11\x76"),          # MRU = 4470
        (OPT_AUTH_PROTOCOL, b"\xc0\x22"), # CHAP
        (OPT_MAGIC_NUMBER, b"\x01\x02\x03\x04"),
        (OPT_PFC, b""),                  # Protocol-Field-Compression
        (OPT_ACFC, b""),                 # Address/Control-Field-Compression
    ]
    result = lcp_negotiate(proposed,
                           peer_supports={OPT_MRU, OPT_AUTH_PROTOCOL,
                                           OPT_MAGIC_NUMBER, OPT_PFC, OPT_ACFC},
                           on_pos=True)
    code_name = {1: "Configure-Request", 2: "Configure-Ack",
                 3: "Configure-Nak", 4: "Configure-Reject"}[result["response_code"]]
    print("LCP negotiation over SONET (RFC 2615: reject ACFC/PFC on POS):")
    print(f"  Request bytes:    {result['request'].hex()}")
    print(f"  Peer response:    {code_name}")
    print(f"  Options acked:    {[t for t,_ in result['acked']]}")
    print(f"  Options rejected: {result['rejected']}")
    print("  (ACFC/PFC rejected on POS even though supported - savings "
          "negligible at OC-48)\n")

    print("=== State machine walk ===")
    for state in ["DEAD", "ESTABLISH", "AUTHENTICATE", "NETWORK", "OPEN"]:
        print(f"  -> {state}")
    print("  (LCP Terminate-Request / carrier loss -> TERMINATE -> DEAD)")


if __name__ == "__main__":
    main()
