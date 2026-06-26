from __future__ import annotations
import hashlib
import hmac
import os
import struct
import textwrap

SRC_HOST = bytes([10, 1, 1, 5])
DST_HOST = bytes([10, 2, 1, 9])
SRC_GW   = bytes([192, 168, 100, 1])
DST_GW   = bytes([192, 168, 200, 1])

AH_PROTO  = 51
ESP_PROTO = 50
ICV_LEN   = 12
BLOCK     = 16

MAC_KEY = b"mac-key-for-lab-demo-32-bytes!!!"
ENC_KEY = b"enc-key-for-lab-demo-32-bytes!!!"

SPI_AH_TRANSPORT  = 0x0A000001
SPI_ESP_TRANSPORT = 0x0B000001
SPI_AH_TUNNEL     = 0x0C000001
SPI_ESP_TUNNEL    = 0x0D000001

PAYLOAD = b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"


def ipv4_header(src: bytes, dst: bytes, proto: int, payload_len: int) -> bytes:
    total = 20 + payload_len
    return struct.pack("!BBHHHBBH4s4s",
        0x45, 0, total, 0, 0, 64, proto, 0, src, dst)


def tcp_header(sport: int, dport: int) -> bytes:
    return struct.pack("!HHLLBBHHH",
        sport, dport, 1000, 0, 0x50, 0x18, 65535, 0, 0)


def zero_mutable(ip_hdr: bytes) -> bytes:
    h = bytearray(ip_hdr)
    h[8]  = 0
    h[9]  = 0
    h[10] = 0
    h[11] = 0
    return bytes(h)


def icv(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha1).digest()[:ICV_LEN]


def keystream(key: bytes, iv_bytes: bytes, length: int) -> bytes:
    out = b""
    ctr = 0
    while len(out) < length:
        out += hmac.new(key, iv_bytes + struct.pack("!Q", ctr),
                        hashlib.sha256).digest()
        ctr += 1
    return out[:length]


def pad_payload(data: bytes) -> tuple[bytes, int]:
    pad_needed = (BLOCK - (len(data) + 2) % BLOCK) % BLOCK
    padding = bytes(range(1, pad_needed + 1))
    return data + padding, pad_needed


def hexdump(label: str, data: bytes) -> None:
    print(f"  {label} ({len(data)} bytes):")
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hex_part  = " ".join(f"{b:02x}" for b in chunk)
        char_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"    {i:04x}  {hex_part:<47}  {char_part}")


def print_field(name: str, value: bytes | int, note: str = "") -> None:
    if isinstance(value, int):
        print(f"    {name:<22} = 0x{value:08x}  {note}")
    else:
        print(f"    {name:<22} = {value.hex()}  {note}")


def section(title: str) -> None:
    bar = "=" * 72
    print(f"\n{bar}\n  {title}\n{bar}")


def build_ah_transport(
    inner_ip: bytes, tcp_hdr: bytes, payload: bytes
) -> tuple[bytes, bytes]:
    ah_fixed = struct.pack("!BBHII", 6, 4, 0, SPI_AH_TRANSPORT, 1)
    zeroed = zero_mutable(inner_ip)
    zeroed_outer = bytearray(zeroed)
    zeroed_outer[9] = AH_PROTO
    auth_input = bytes(zeroed_outer) + ah_fixed + bytes(ICV_LEN) + tcp_hdr + payload
    auth_value = icv(MAC_KEY, auth_input)
    outer = bytearray(inner_ip)
    outer[9] = AH_PROTO
    packet = bytes(outer) + ah_fixed + auth_value + tcp_hdr + payload
    return packet, auth_value


def parse_ah_transport(packet: bytes) -> dict:
    outer_ip = packet[:20]
    next_hdr, payload_len, reserved, spi, seq = struct.unpack("!BBHII", packet[20:32])
    auth_value = packet[32:44]
    rest = packet[44:]
    zeroed = bytearray(zero_mutable(outer_ip))
    zeroed[9] = AH_PROTO
    recomputed = icv(MAC_KEY,
                     bytes(zeroed) + packet[20:32] + bytes(ICV_LEN) + rest)
    return {
        "next_header": next_hdr,
        "payload_len": payload_len,
        "spi": spi,
        "seq": seq,
        "icv_received": auth_value,
        "icv_valid": recomputed == auth_value,
        "protected_payload_len": len(rest),
    }


def build_esp_transport(
    inner_ip: bytes, tcp_hdr: bytes, payload: bytes
) -> tuple[bytes, bytes, bytes, bytes]:
    iv_bytes = os.urandom(BLOCK)
    plaintext = tcp_hdr + payload
    padded, pad_len = pad_payload(plaintext)
    trailer = bytes([pad_len, 6])
    pt_with_trailer = padded + trailer
    ks = keystream(ENC_KEY, iv_bytes, len(pt_with_trailer))
    ciphertext = bytes(a ^ b for a, b in zip(pt_with_trailer, ks))
    esp_hdr = struct.pack("!II", SPI_ESP_TRANSPORT, 1)
    auth_input = esp_hdr + iv_bytes + ciphertext
    auth_value = icv(MAC_KEY, auth_input)
    outer = bytearray(inner_ip)
    outer[9] = ESP_PROTO
    packet = bytes(outer) + esp_hdr + iv_bytes + ciphertext + auth_value
    return packet, iv_bytes, ciphertext, auth_value


def parse_esp_transport(packet: bytes) -> dict:
    outer_ip = packet[:20]
    spi, seq = struct.unpack("!II", packet[20:28])
    iv_bytes  = packet[28:44]
    body      = packet[44:]
    ciphertext = body[:-ICV_LEN]
    auth_received = body[-ICV_LEN:]
    auth_input = packet[20:28] + iv_bytes + ciphertext
    recomputed = icv(MAC_KEY, auth_input)
    icv_ok = recomputed == auth_received
    ks = keystream(ENC_KEY, iv_bytes, len(ciphertext))
    plaintext = bytes(a ^ b for a, b in zip(ciphertext, ks))
    pad_len = plaintext[-2]
    next_hdr = plaintext[-1]
    actual_payload = plaintext[:-(pad_len + 2)]
    return {
        "spi": spi,
        "seq": seq,
        "iv": iv_bytes,
        "icv_received": auth_received,
        "icv_valid": icv_ok,
        "pad_len": pad_len,
        "next_header": next_hdr,
        "decrypted_len": len(actual_payload),
    }


def build_ah_tunnel(
    inner_ip: bytes, tcp_hdr: bytes, payload: bytes
) -> tuple[bytes, bytes]:
    inner_pkt = inner_ip + tcp_hdr + payload
    ah_fixed = struct.pack("!BBHII", 4, 4, 0, SPI_AH_TUNNEL, 1)
    ah_len = len(ah_fixed) + ICV_LEN
    outer = ipv4_header(SRC_GW, DST_GW, AH_PROTO,
                        ah_len + len(inner_pkt))
    zeroed_outer = bytearray(zero_mutable(outer))
    zeroed_outer[9] = AH_PROTO
    auth_input = bytes(zeroed_outer) + ah_fixed + bytes(ICV_LEN) + inner_pkt
    auth_value = icv(MAC_KEY, auth_input)
    packet = outer + ah_fixed + auth_value + inner_pkt
    return packet, auth_value


def parse_ah_tunnel(packet: bytes) -> dict:
    outer_ip = packet[:20]
    next_hdr, payload_len, reserved, spi, seq = struct.unpack("!BBHII", packet[20:32])
    auth_value = packet[32:44]
    inner_pkt = packet[44:]
    zeroed = bytearray(zero_mutable(outer_ip))
    zeroed[9] = AH_PROTO
    recomputed = icv(MAC_KEY,
                     bytes(zeroed) + packet[20:32] + bytes(ICV_LEN) + inner_pkt)
    inner_src = ".".join(str(b) for b in inner_pkt[12:16])
    inner_dst = ".".join(str(b) for b in inner_pkt[16:20])
    return {
        "outer_src": ".".join(str(b) for b in outer_ip[12:16]),
        "outer_dst": ".".join(str(b) for b in outer_ip[16:20]),
        "next_header": next_hdr,
        "spi": spi,
        "seq": seq,
        "icv_received": auth_value,
        "icv_valid": recomputed == auth_value,
        "inner_src": inner_src,
        "inner_dst": inner_dst,
    }


def build_esp_tunnel(
    inner_ip: bytes, tcp_hdr: bytes, payload: bytes
) -> tuple[bytes, bytes, bytes, bytes]:
    iv_bytes = os.urandom(BLOCK)
    plaintext = inner_ip + tcp_hdr + payload
    padded, pad_len = pad_payload(plaintext)
    trailer = bytes([pad_len, 4])
    pt_with_trailer = padded + trailer
    ks = keystream(ENC_KEY, iv_bytes, len(pt_with_trailer))
    ciphertext = bytes(a ^ b for a, b in zip(pt_with_trailer, ks))
    esp_hdr = struct.pack("!II", SPI_ESP_TUNNEL, 1)
    auth_input = esp_hdr + iv_bytes + ciphertext
    auth_value = icv(MAC_KEY, auth_input)
    total_inner = len(esp_hdr) + BLOCK + len(ciphertext) + ICV_LEN
    outer = ipv4_header(SRC_GW, DST_GW, ESP_PROTO, total_inner)
    packet = outer + esp_hdr + iv_bytes + ciphertext + auth_value
    return packet, iv_bytes, ciphertext, auth_value


def parse_esp_tunnel(packet: bytes) -> dict:
    outer_ip = packet[:20]
    spi, seq = struct.unpack("!II", packet[20:28])
    iv_bytes  = packet[28:44]
    body      = packet[44:]
    ciphertext = body[:-ICV_LEN]
    auth_received = body[-ICV_LEN:]
    auth_input = packet[20:28] + iv_bytes + ciphertext
    recomputed = icv(MAC_KEY, auth_input)
    icv_ok = recomputed == auth_received
    ks = keystream(ENC_KEY, iv_bytes, len(ciphertext))
    plaintext = bytes(a ^ b for a, b in zip(ciphertext, ks))
    pad_len = plaintext[-2]
    next_hdr = plaintext[-1]
    actual = plaintext[:-(pad_len + 2)]
    inner_src = ".".join(str(b) for b in actual[12:16])
    inner_dst = ".".join(str(b) for b in actual[16:20])
    return {
        "outer_src": ".".join(str(b) for b in outer_ip[12:16]),
        "outer_dst": ".".join(str(b) for b in outer_ip[16:20]),
        "spi": spi,
        "seq": seq,
        "iv": iv_bytes,
        "icv_received": auth_received,
        "icv_valid": icv_ok,
        "pad_len": pad_len,
        "next_header": next_hdr,
        "inner_src": inner_src,
        "inner_dst": inner_dst,
        "decrypted_payload_len": len(actual) - 20,
    }


def main() -> None:
    tcp_hdr = tcp_header(54321, 80)
    inner_ip = ipv4_header(SRC_HOST, DST_HOST, 6, len(tcp_hdr) + len(PAYLOAD))

    section("1 of 4  —  AH TRANSPORT MODE  (RFC 4302)")
    print("""
  Packet structure:
    [ IP Header | AH Header | TCP Header | Payload ]
    proto=51      next=6      (in clear)   (in clear)
                  SPI + Seq
                  ICV covers: zeroed-IP + AH(ICV=0) + TCP + payload
""")
    pkt_ah_t, auth_ah_t = build_ah_transport(inner_ip, tcp_hdr, PAYLOAD)
    hexdump("AH-transport packet", pkt_ah_t)
    r = parse_ah_transport(pkt_ah_t)
    print()
    print("  Parsed fields:")
    print_field("Next Header",  r["next_header"], "(6 = TCP)")
    print_field("SPI",          r["spi"])
    print_field("Sequence",     r["seq"])
    print_field("ICV (rcvd)",   r["icv_received"])
    print(f"    {'ICV valid':<22} = {r['icv_valid']}")
    print(f"    {'Overhead':<22} = {len(pkt_ah_t) - len(inner_ip) - len(tcp_hdr) - len(PAYLOAD)} bytes (12 fixed + {ICV_LEN} ICV)")
    assert r["icv_valid"], "AH transport ICV check failed"

    section("2 of 4  —  ESP TRANSPORT MODE  (RFC 4303)")
    print("""
  Packet structure:
    [ IP Header | ESP Header | IV | Ciphertext | ICV ]
    proto=50      SPI + Seq    16B  (TCP+payload  12B
                                    +pad+trailer)
                  ICV covers: SPI + Seq + IV + ciphertext
""")
    pkt_esp_t, iv_esp_t, ct_esp_t, auth_esp_t = build_esp_transport(
        inner_ip, tcp_hdr, PAYLOAD)
    hexdump("ESP-transport packet", pkt_esp_t)
    r = parse_esp_transport(pkt_esp_t)
    print()
    print("  Parsed fields:")
    print_field("SPI",          r["spi"])
    print_field("Sequence",     r["seq"])
    print_field("IV",           r["iv"])
    print_field("ICV (rcvd)",   r["icv_received"])
    print(f"    {'ICV valid':<22} = {r['icv_valid']}")
    print(f"    {'Next Header':<22} = {r['next_header']}  (6 = TCP, recovered from decrypted trailer)")
    print(f"    {'Pad Length':<22} = {r['pad_len']} bytes")
    print(f"    {'Decrypted len':<22} = {r['decrypted_len']} bytes")
    print(f"    {'Overhead':<22} = {len(pkt_esp_t) - len(inner_ip) - len(tcp_hdr) - len(PAYLOAD)} bytes (8 ESP + 16 IV + pad + trailer + 12 ICV)")
    assert r["icv_valid"], "ESP transport ICV check failed"

    section("3 of 4  —  AH TUNNEL MODE  (RFC 4302)")
    print("""
  Packet structure:
    [ Outer IP | AH Header | Inner IP | TCP Header | Payload ]
    src=gw-A    next=4       src=host   (in clear)   (in clear)
    dst=gw-B    SPI + Seq    dst=host
    proto=51    ICV covers: zeroed-outer-IP + AH(ICV=0) + inner-IP + TCP + payload
""")
    pkt_ah_tn, auth_ah_tn = build_ah_tunnel(inner_ip, tcp_hdr, PAYLOAD)
    hexdump("AH-tunnel packet", pkt_ah_tn)
    r = parse_ah_tunnel(pkt_ah_tn)
    print()
    print("  Parsed fields:")
    print(f"    {'Outer src':<22} = {r['outer_src']}")
    print(f"    {'Outer dst':<22} = {r['outer_dst']}")
    print_field("Next Header",  r["next_header"], "(4 = IP-in-IP)")
    print_field("SPI",          r["spi"])
    print_field("Sequence",     r["seq"])
    print_field("ICV (rcvd)",   r["icv_received"])
    print(f"    {'ICV valid':<22} = {r['icv_valid']}")
    print(f"    {'Inner src':<22} = {r['inner_src']}")
    print(f"    {'Inner dst':<22} = {r['inner_dst']}")
    print(f"    {'Overhead':<22} = {len(pkt_ah_tn) - len(inner_ip) - len(tcp_hdr) - len(PAYLOAD)} bytes (20 outer-IP + 12 AH-fixed + 12 ICV)")
    assert r["icv_valid"], "AH tunnel ICV check failed"

    section("4 of 4  —  ESP TUNNEL MODE  (RFC 4303)")
    print("""
  Packet structure:
    [ Outer IP | ESP Header | IV | Ciphertext         | ICV ]
    src=gw-A    SPI + Seq    16B  (inner-IP + TCP      12B
    dst=gw-B                      + payload + trailer)
    proto=50    ICV covers: SPI + Seq + IV + ciphertext
    Inner IP header, TCP, and payload are ALL encrypted.
""")
    pkt_esp_tn, iv_esp_tn, ct_esp_tn, auth_esp_tn = build_esp_tunnel(
        inner_ip, tcp_hdr, PAYLOAD)
    hexdump("ESP-tunnel packet", pkt_esp_tn)
    r = parse_esp_tunnel(pkt_esp_tn)
    print()
    print("  Parsed fields:")
    print(f"    {'Outer src':<22} = {r['outer_src']}")
    print(f"    {'Outer dst':<22} = {r['outer_dst']}")
    print_field("SPI",          r["spi"])
    print_field("Sequence",     r["seq"])
    print_field("IV",           r["iv"])
    print_field("ICV (rcvd)",   r["icv_received"])
    print(f"    {'ICV valid':<22} = {r['icv_valid']}")
    print(f"    {'Next Header':<22} = {r['next_header']}  (4 = IP-in-IP, recovered from decrypted trailer)")
    print(f"    {'Pad Length':<22} = {r['pad_len']} bytes")
    print(f"    {'Inner src':<22} = {r['inner_src']}  (recovered after decrypt)")
    print(f"    {'Inner dst':<22} = {r['inner_dst']}  (recovered after decrypt)")
    print(f"    {'Overhead':<22} = {len(pkt_esp_tn) - len(inner_ip) - len(tcp_hdr) - len(PAYLOAD)} bytes (20 outer-IP + 8 ESP + 16 IV + pad + trailer + 12 ICV)")
    assert r["icv_valid"], "ESP tunnel ICV check failed"

    section("Summary: AH vs ESP, transport vs tunnel")
    print()
    rows = [
        ("Mode",          "Protocol", "Overhead", "Encrypted",            "ICV covers",                      "NAT-safe"),
        ("transport",     "AH",       "24 B",     "nothing",              "zeroed-outer-IP + AH + TCP + data","no"),
        ("transport",     "ESP",      "~53 B",    "TCP + data",           "SPI + Seq + IV + ciphertext",      "yes (NAT-T)"),
        ("tunnel",        "AH",       "44 B",     "nothing",              "zeroed-outer-IP + AH + inner-IP + TCP + data","no"),
        ("tunnel",        "ESP",      "~73 B",    "inner-IP + TCP + data","SPI + Seq + IV + ciphertext",      "yes (NAT-T)"),
    ]
    col_w = [12, 10, 10, 25, 47, 12]
    for row in rows:
        print("  " + "  ".join(str(v).ljust(col_w[i]) for i, v in enumerate(row)))

    print()
    print("All four round-trip assertions passed.")


if __name__ == "__main__":
    main()
