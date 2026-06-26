#!/usr/bin/env python3
"""ESP tunnel-mode simulator for an IPsec site-to-site VPN.

Builds a synthetic IPv4/TCP inner packet for a private 10.10.0.0/16 source
and destination, then wraps it in an ESP tunnel-mode packet: outer IP header
(protocol 50), ESP header (SPI + Sequence Number + IV), padding to a 16-byte
AES block boundary, Pad Length, Next Header, and HMAC-SHA-256 ICV. The
receiver side verifies the ICV, walks the anti-replay window, and detects
replay. The cipher is an XOR-with-keyed-PRF stand-in for AES-CBC -- the
goal is to exercise the *layout* and the *protocol state machine*, not to
implement a real cipher. Pure stdlib, no pip deps.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import struct
from dataclasses import dataclass, field

ESP_PROTOCOL = 50
IPPROTO_IPIP = 4
AES_BLOCK = 16
HMAC_LEN = 32
IV_LEN = 16


@dataclass(frozen=True)
class InnerPacket:
    src: str
    dst: str
    proto: int
    payload: bytes

    def encode(self) -> bytes:
        return (
            struct.pack(
                "!BBHHHBBH4s4s", 0x45, 0, 20 + len(self.payload),
                0, 0, 64, self.proto, 0,
                bytes(int(x) for x in self.src.split(".")),
                bytes(int(x) for x in self.dst.split(".")),
            ) + self.payload
        )


@dataclass
class SecurityAssociation:
    spi: int
    dest_ip: str
    enc_key: bytes
    auth_key: bytes
    seq: int = 0
    lifetime: int = 2_000_000
    window: int = 32
    seen: set[int] = field(default_factory=set)
    min_seen: int = 0

    def rotate_spi(self) -> int:
        self.spi = (self.spi + 0x100) & 0xFFFFFFFF
        return self.spi

    def mark_seen(self, seq: int) -> str:
        if seq < self.min_seen - self.window:
            return "REPLAY_TOO_OLD"
        if seq in self.seen:
            return "REPLAY_DETECTED"
        self.seen.add(seq)
        if seq >= self.min_seen + self.window:
            self.min_seen = seq - self.window + 1
        return "ACCEPTED"


def _kv(plain: bytes, key: bytes) -> bytes:
    out = bytearray()
    prev = hashlib.sha256(key + b"iv").digest()[:AES_BLOCK]
    for off in range(0, len(plain), AES_BLOCK):
        ks = hashlib.sha256(key + prev).digest()[:AES_BLOCK]
        block = (plain[off : off + AES_BLOCK] + b"\x00" * AES_BLOCK)[:AES_BLOCK]
        out.extend(bytes(a ^ b ^ c for a, b, c in zip(block, ks, prev)))
        prev = bytes(out[off : off + AES_BLOCK])
    return bytes(out)


def _vk(cipher: bytes, key: bytes) -> bytes:
    out = bytearray()
    prev = hashlib.sha256(key + b"iv").digest()[:AES_BLOCK]
    for off in range(0, len(cipher), AES_BLOCK):
        ks = hashlib.sha256(key + prev).digest()[:AES_BLOCK]
        block = cipher[off : off + AES_BLOCK]
        out.extend(bytes(a ^ b ^ c for a, b, c in zip(block, ks, prev)))
        prev = block
    return bytes(out)


def wrap_esp(inner: bytes, sa: SecurityAssociation, src: str, dst: str) -> bytes:
    pad_len = (-len(inner)) % AES_BLOCK or AES_BLOCK
    padded = inner + b"\x00" * pad_len
    cipher = _kv(padded, sa.enc_key)
    iv = secrets.token_bytes(IV_LEN)
    head = struct.pack("!II", sa.spi, sa.seq) + iv
    trailer = struct.pack("!BB", pad_len, IPPROTO_IPIP)
    icv = hmac.new(sa.auth_key, head + cipher + trailer, hashlib.sha256).digest()
    esp = head + cipher + trailer + icv
    outer = struct.pack(
        "!BBHHHBBH4s4s", 0x45, 0, 20 + len(esp), 0, 0, 64,
        ESP_PROTOCOL, 0,
        bytes(int(x) for x in src.split(".")),
        bytes(int(x) for x in dst.split(".")),
    )
    return outer + esp


def unwrap_esp(pkt: bytes, sa: SecurityAssociation) -> tuple[bytes, int, int, str]:
    if pkt[9] != ESP_PROTOCOL:
        return b"", 0, 0, "BAD_PROTOCOL"
    esp = pkt[20:]
    spi, seq = struct.unpack("!II", esp[:8])
    cipher = esp[8 + IV_LEN : -HMAC_LEN - 2]
    pad_len, _ = struct.unpack("!BB", esp[-HMAC_LEN - 2 : -HMAC_LEN])
    trailer = esp[-HMAC_LEN - 2 : -HMAC_LEN]
    expected = hmac.new(sa.auth_key, esp[: -HMAC_LEN], hashlib.sha256).digest()
    if not hmac.compare_digest(esp[-HMAC_LEN:], expected):
        return b"", spi, seq, "BAD_ICV"
    verdict = sa.mark_seen(seq)
    if verdict != "ACCEPTED":
        return b"", spi, seq, verdict
    plain = _vk(cipher, sa.enc_key)[: len(cipher) - pad_len]
    return plain, spi, seq, "ACCEPTED"


def _hex(label: str, data: bytes) -> None:
    print(f"  {label}  ({len(data)} B)")
    for off in range(0, len(data), 16):
        chunk = data[off : off + 16]
        h = " ".join(f"{b:02x}" for b in chunk)
        a = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"    {off:04x}  {h:<48}  {a}")


def main() -> None:
    print("=" * 70)
    print("ESP TUNNEL-MODE SIMULATOR  --  IPsec site-to-site VPN")
    print("=" * 70)

    inner_pkt = InnerPacket(
        "10.10.0.50", "10.10.1.50", 6,
        b"GET /inventory HTTP/1.1\r\nHost: erp\r\n\r\n",
    )
    sa = SecurityAssociation(
        spi=0xC0FFEE01, dest_ip="198.51.100.7",
        enc_key=hashlib.sha256(b"site-a-enc-key").digest(),
        auth_key=hashlib.sha256(b"site-a-auth-key").digest(),
    )
    OUTER_SRC, OUTER_DST = "203.0.113.5", "198.51.100.7"
    inner = inner_pkt.encode()

    print(f"\nInner: {inner_pkt.src} -> {inner_pkt.dst}, TCP, {len(inner_pkt.payload)} B")
    _hex("inner (cleartext on the LAN)", inner)
    needle = inner_pkt.src.encode()
    print(f"  inner source {inner_pkt.src!r} as raw bytes present: {needle in inner}")

    print(f"\nFirst ESP packet (seq=0, SPI=0x{sa.spi:08X}):")
    pkt0 = wrap_esp(inner, sa, OUTER_SRC, OUTER_DST)
    _hex("on-wire ESP packet", pkt0)
    print(f"  inner source {inner_pkt.src!r} in encrypted packet: {needle in pkt0}")

    print("\nWalking the sequence counter through 8 packets:")
    for i in range(8):
        sa.seq = i
        pkt = wrap_esp(inner, sa, OUTER_SRC, OUTER_DST)
        if pkt[24:28] != struct.pack("!I", sa.spi):
            sa.rotate_spi()
            pkt = wrap_esp(inner, sa, OUTER_SRC, OUTER_DST)
        print(f"  pkt {i}  SPI=0x{sa.spi:08x}  Seq={i}  total_len={len(pkt)} B")

    print("\nReceiver-side verification (re-derive ICV, walk anti-replay):")
    sa.seq = 3
    pkt3 = wrap_esp(inner, sa, OUTER_SRC, OUTER_DST)
    d, _, sq, v = unwrap_esp(pkt3, sa)
    print(f"  first verify seq={sq} -> {v}  inner src bytes 12-20: {d[12:20]!r}")
    d2, _, sq2, v2 = unwrap_esp(pkt3, sa)
    print(f"  replay verify seq={sq2} -> {v2}  decoded: {d2!r}")

    print("\nRekey demonstration (lifetime=4 packets):")
    sa2 = SecurityAssociation(
        spi=0xC0FFEE01, dest_ip="198.51.100.7",
        enc_key=sa.enc_key, auth_key=sa.auth_key, lifetime=4,
    )
    for i in range(8):
        if sa2.seq >= sa2.lifetime:
            new_spi = sa2.rotate_spi()
            print(f"  rekeying at seq {sa2.seq} -> new SPI 0x{new_spi:08x}")
            sa2.seq = 0
        pkt = wrap_esp(inner, sa2, OUTER_SRC, OUTER_DST)
        print(f"  pkt {i}  SPI=0x{sa2.spi:08x}  Seq={sa2.seq}  total_len={len(pkt)} B")
        sa2.seq += 1

    print("\nDone. Compare the on-wire hex to RFC 4303 figure 1.")


if __name__ == "__main__":
    main()
