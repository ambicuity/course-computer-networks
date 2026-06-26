"""IPsec ESP (RFC 4303) packet builder and verifier (stdlib-only).

We model an ESP SA, build a packet with a stand-in AES-CTR-style
keystream (HMAC-SHA256 counter mode), and verify/decrypt on the
receiver. The wire format is identical to RFC 4303; only the cipher
core is replaced for stdlib portability.
"""

from __future__ import annotations

import hashlib
import hmac
import struct
from dataclasses import dataclass


NEXT_HEADER_TCP = 6
NEXT_HEADER_UDP = 17
NEXT_HEADER_IPV4 = 4
NEXT_HEADER_ICMP = 1


@dataclass
class ESPContext:
    spi: int
    dst: str
    enc_key: bytes
    mac_key: bytes
    seq: int = 1
    mode: str = "transport"
    block_size: int = 16
    iv_len: int = 8
    icv_len: int = 16


def _keystream(key: bytes, iv: bytes, length: int) -> bytes:
    """Counter-mode keystream from HMAC-SHA256.

    Generates blocks of 32 bytes by HMAC-ing (key, iv, counter). Real
    AES-CTR uses the same shape; the only difference is the primitive.
    """
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(
            key, iv + counter.to_bytes(8, "big"), hashlib.sha256
        ).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def _pad(payload: bytes, block_size: int) -> tuple[bytes, int]:
    """ESP padding: 1..block_size bytes such that (len(payload) + pad) % block == 0
    and the pad length is encoded as 1..255."""
    pad_len = block_size - ((len(payload) + 2) % block_size)
    if pad_len < 1:
        pad_len += block_size
    return bytes([0x01] * pad_len), pad_len


def build_esp_packet(ctx: ESPContext, payload: bytes, next_header: int) -> bytes:
    iv = hashlib.sha256(ctx.enc_key + ctx.dst.encode() + b"|iv").digest()[: ctx.iv_len]
    pad, pad_len = _pad(payload, ctx.block_size)
    trailer = pad + bytes([pad_len, next_header])
    plaintext = payload + trailer
    ks = _keystream(ctx.enc_key, iv, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, ks))
    header = struct.pack(">II", ctx.spi & 0xFFFFFFFF, ctx.seq & 0xFFFFFFFF)
    body = header + iv + ciphertext
    icv = hmac.new(ctx.mac_key, body, hashlib.sha256).digest()[: ctx.icv_len]
    return body + icv


def verify_esp_packet(
    ctx: ESPContext, packet: bytes, replay_seen: set[int] | None = None
) -> tuple[bool, bytes, str]:
    if len(packet) < 8 + ctx.iv_len + ctx.icv_len:
        return False, b"", "packet too short"
    spi, seq = struct.unpack(">II", packet[:8])
    if spi != ctx.spi:
        return False, b"", "SPI mismatch"
    if replay_seen is not None:
        if seq in replay_seen:
            return False, b"", "replay detected"
        replay_seen.add(seq)
    body = packet[: -ctx.icv_len]
    icv_received = packet[-ctx.icv_len :]
    icv_expected = hmac.new(ctx.mac_key, body, hashlib.sha256).digest()[: ctx.icv_len]
    if not hmac.compare_digest(icv_expected, icv_received):
        return False, b"", "ICV mismatch"
    iv = body[8 : 8 + ctx.iv_len]
    ciphertext = body[8 + ctx.iv_len :]
    ks = _keystream(ctx.enc_key, iv, len(ciphertext))
    plaintext = bytes(a ^ b for a, b in zip(ciphertext, ks))
    pad_len = plaintext[-2]
    next_header = plaintext[-1]
    inner = plaintext[: -2 - pad_len]
    return True, inner, f"ok next_header={next_header}"


def main() -> None:
    """Build, verify, decrypt, tamper."""
    ctx = ESPContext(
        spi=0xCAFE, dst="10.0.0.2",
        enc_key=b"e" * 32, mac_key=b"m" * 32,
        seq=1, mode="transport", block_size=16, iv_len=8, icv_len=16,
    )
    payload = b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
    pkt = build_esp_packet(ctx, payload, next_header=NEXT_HEADER_TCP)
    print(f"ESP packet length: {len(pkt)}")
    ok, plaintext, reason = verify_esp_packet(ctx, pkt)
    print(f"verify ok: {ok}, reason: {reason}")
    print(f"plaintext: {plaintext!r}")
    # Tamper with ciphertext (one byte).
    tampered = bytearray(pkt)
    tampered[20] ^= 0x01
    ok2, _, reason2 = verify_esp_packet(ctx, bytes(tampered))
    print(f"tampered verify: ok={ok2} reason={reason2}")
    # Replay.
    seen: set[int] = set()
    verify_esp_packet(ctx, pkt, replay_seen=seen)
    ok3, _, reason3 = verify_esp_packet(ctx, pkt, replay_seen=seen)
    print(f"replay verify: ok={ok3} reason={reason3}")


if __name__ == "__main__":
    main()