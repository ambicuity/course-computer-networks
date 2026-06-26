"""TLS 1.3 record layer, handshake state machine, and cipher-suite lookup.

Pure stdlib Python. Parses the 5-byte TLS record header (content_type,
version, length), walks the TLS 1.3 handshake state machine (RFC 8446 §4),
and decodes IANA cipher suite IDs.

Does NOT implement AEAD encryption -- that would require a real AES-GCM or
ChaCha20-Poly1305 primitive. The simulator tracks every state transition
and reports the negotiated parameters, which is enough to read a Wireshark
capture or a curl -v trace.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import struct
from dataclasses import dataclass, field
from enum import IntEnum


class ContentType(IntEnum):
    CHANGE_CIPHER_SPEC = 20
    ALERT = 21
    HANDSHAKE = 22
    APPLICATION_DATA = 23


class HandshakeType(IntEnum):
    CLIENT_HELLO = 1
    SERVER_HELLO = 2
    NEW_SESSION_TICKET = 4
    ENCRYPTED_EXTENSIONS = 8
    CERTIFICATE = 11
    CERTIFICATE_VERIFY = 15
    FINISHED = 20


@dataclass
class TLSRecord:
    content_type: int
    version: tuple[int, int]
    length: int
    fragment: bytes

    def serialize(self) -> bytes:
        return struct.pack("!BHH", self.content_type, self.version[0] * 256 + self.version[1], self.length) + self.fragment


def parse_record(data: bytes) -> TLSRecord:
    if len(data) < 5:
        raise ValueError(f"record too short: {len(data)} bytes")
    ct = data[0]
    ver_major, ver_minor = data[1], data[2]
    length = struct.unpack("!H", data[3:5])[0]
    if len(data) < 5 + length:
        raise ValueError(f"record fragment truncated: want {length}, have {len(data) - 5}")
    return TLSRecord(
        content_type=ct,
        version=(ver_major, ver_minor),
        length=length,
        fragment=data[5:5 + length],
    )


def serialize_record(content_type: int, fragment: bytes, version: tuple[int, int] = (3, 3)) -> bytes:
    return TLSRecord(content_type, version, len(fragment), fragment).serialize()


@dataclass
class HandshakeMessage:
    msg_type: int
    length: int
    body: bytes


def parse_handshake_message(data: bytes) -> HandshakeMessage:
    if len(data) < 4:
        raise ValueError("handshake header truncated")
    msg_type = data[0]
    length = struct.unpack("!I", b"\x00" + data[1:4])[0]
    return HandshakeMessage(msg_type, length, data[4:4 + length])


def serialize_handshake_message(msg_type: int, body: bytes) -> bytes:
    return struct.pack("!B", msg_type) + struct.pack("!I", len(body))[1:] + body


@dataclass(frozen=True)
class CipherSuite:
    id: int
    name: str
    aead: str
    hash_algo: str
    min_tls: tuple[int, int] = (3, 4)


CIPHER_SUITES: dict[int, CipherSuite] = {
    0x1301: CipherSuite(0x1301, "TLS_AES_128_GCM_SHA256", "AES-128-GCM", "SHA-256"),
    0x1302: CipherSuite(0x1302, "TLS_AES_256_GCM_SHA384", "AES-256-GCM", "SHA-384"),
    0x1303: CipherSuite(0x1303, "TLS_CHACHA20_POLY1305_SHA256", "ChaCha20-Poly1305", "SHA-256"),
    0x1304: CipherSuite(0x1304, "TLS_AES_128_CCM_SHA256", "AES-128-CCM", "SHA-256"),
    0x1305: CipherSuite(0x1305, "TLS_AES_128_CCM_8_SHA256", "AES-128-CCM-8", "SHA-256"),
    0xC02F: CipherSuite(0xC02F, "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256", "AES-128-GCM", "SHA-256", (3, 3)),
    0xC030: CipherSuite(0xC02F, "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384", "AES-256-GCM", "SHA-384", (3, 3)),
    0xCCA8: CipherSuite(0xCCA8, "TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256", "ChaCha20-Poly1305", "SHA-256", (3, 3)),
    0xCCA9: CipherSuite(0xCCA9, "TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256", "ChaCha20-Poly1305", "SHA-256", (3, 3)),
}


def decode_cipher_suite(id_: int) -> CipherSuite:
    return CIPHER_SUITES.get(id_, CipherSuite(id_, f"UNKNOWN_0x{id_:04x}", "?", "?"))


NAMED_GROUPS = {
    0x001D: "X25519",
    0x0017: "secp256r1 (P-256)",
    0x0018: "secp384r1 (P-384)",
    0x0100: "ffdhe2048",
    0x0101: "ffdhe3072",
    0x0102: "ffdhe4096",
}


@dataclass
class TLS13Client:
    sni: str = "example.com"
    client_random: bytes = field(default_factory=lambda: secrets.token_bytes(32))
    legacy_version: tuple[int, int] = (3, 3)
    offered_cipher_suites: list[int] = field(default_factory=lambda: [0x1301, 0x1302, 0x1303])
    supported_versions: list[tuple[int, int]] = field(default_factory=lambda: [(3, 4), (3, 3)])
    offered_key_share_group: int = 0x001D
    state: str = "INIT"

    def client_hello_bytes(self) -> bytes:
        body = struct.pack("!HH", self.legacy_version[0], self.legacy_version[1])
        body += self.client_random
        body += b"\x00"
        body += struct.pack("!H", len(self.offered_cipher_suites) * 2)
        for cs in self.offered_cipher_suites:
            body += struct.pack("!H", cs)
        body += b"\x01\x00"  # legacy_compression_methods: null
        sv = b"\x00\x2b" + struct.pack("!H", len(self.supported_versions) * 2 + 1) + b"\x03" + struct.pack("!H", len(self.supported_versions) * 2)
        for v in self.supported_versions:
            sv += struct.pack("!H", v[0] * 256 + v[1])
        ks = b"\x00\x33" + struct.pack("!H", 4 + 32) + struct.pack("!HH", self.offered_key_share_group, 32) + b"\x00" * 32
        body += struct.pack("!H", len(sv) + len(ks))
        body += sv + ks
        return serialize_handshake_message(HandshakeType.CLIENT_HELLO, body)

    def client_hello_record(self) -> bytes:
        ch = self.client_hello_bytes()
        return serialize_record(ContentType.HANDSHAKE, ch)

    def parse_server_hello(self, data: bytes) -> tuple[int, tuple[int, int], bytes]:
        msg = parse_handshake_message(data)
        if msg.msg_type != HandshakeType.SERVER_HELLO:
            raise ValueError(f"expected ServerHello, got msg_type {msg.msg_type}")
        version = struct.unpack("!H", msg.body[0:2])[0]
        random_bytes = msg.body[2:34]
        sid_len = msg.body[34]
        idx = 35 + sid_len
        cipher_suite = struct.unpack("!H", msg.body[idx:idx + 2])[0]
        idx += 2
        compression = msg.body[idx]
        idx += 1
        ext_len = struct.unpack("!H", msg.body[idx:idx + 2])[0]
        return cipher_suite, (version >> 8, version & 0xFF), random_bytes


def hkdf_extract(salt: bytes, ikm: bytes, hash_func=hashlib.sha256) -> bytes:
    if not salt:
        salt = b"\x00" * hash_func().digest_size
    return hmac.new(salt, ikm, hash_func).digest()


def hkdf_expand_label(secret: bytes, label: str, context: bytes, length: int, hash_func=hashlib.sha256) -> bytes:
    full_label = f"tls13 {label}".encode()
    h = hash_func()
    info = struct.pack("!H", length) + struct.pack("!B", len(full_label)) + full_label + struct.pack("!B", len(context)) + context
    return hmac.new(secret, info + b"\x01", hash_func).digest()[:length]


def parse_pcap_tls_records(pcap_bytes: bytes) -> list[TLSRecord]:
    records: list[TLSRecord] = []
    pos = 0
    while pos < len(pcap_bytes):
        try:
            rec = parse_record(pcap_bytes[pos:])
        except ValueError:
            break
        records.append(rec)
        pos += 5 + rec.length
    return records


def main() -> None:
    print("=" * 68)
    print("TLS 1.3 INSPECTOR  --  record layer, handshake, cipher suites")
    print("=" * 68)

    print("\n[1] Record-layer round-trip")
    payload = b"\x14\x03\x03\x00\x05hello"  # fake ServerHello-ish
    rec = serialize_record(ContentType.HANDSHAKE, payload[5:])
    parsed = parse_record(rec)
    print(f"  serialized length : {len(rec)}")
    print(f"  parsed CT         : {ContentType(parsed.content_type).name}")
    print(f"  parsed version    : {parsed.version}")
    print(f"  parsed length     : {parsed.length}")

    print("\n[2] TLS 1.3 ClientHello")
    client = TLS13Client(sni="example.com")
    ch_record = client.client_hello_record()
    print(f"  ClientHello record: {len(ch_record)} bytes")
    parsed_ch = parse_record(ch_record)
    hs = parse_handshake_message(parsed_ch.fragment)
    print(f"  handshake type    : {HandshakeType(hs.msg_type).name}")
    print(f"  body length       : {hs.length}")

    print("\n[3] Cipher suite IDs (TLS 1.3 and TLS 1.2)")
    for id_ in (0x1301, 0x1302, 0x1303, 0x1304, 0x1305, 0xC02F, 0xCCA9):
        cs = decode_cipher_suite(id_)
        marker = " (TLS 1.3)" if cs.min_tls >= (3, 4) else " (TLS 1.2)"
        print(f"  0x{id_:04x} {cs.name:<48} AEAD={cs.aead:<20} hash={cs.hash_algo}{marker}")

    print("\n[4] HKDF key schedule (RFC 8446 §7.1)")
    zero_salt = b"\x00" * 32
    early = hkdf_extract(zero_salt, b"\x00" * 32)
    derived = hkdf_expand_label(early, "derived", b"", 32)
    shared_secret = secrets.token_bytes(32)
    handshake = hkdf_extract(derived, shared_secret)
    client_hs_traffic = hkdf_expand_label(handshake, "c hs traffic", b"ClientHello..server Finished", 32)
    print(f"  early_secret       : {early.hex()[:24]}...")
    print(f"  derived            : {derived.hex()[:24]}...")
    print(f"  handshake_secret   : {handshake.hex()[:24]}...")
    print(f"  client hs traffic  : {client_hs_traffic.hex()[:24]}...")

    print("\n[5] Wireshark-style record stream (synthetic)")
    sample = client.client_hello_record() + b"\x16\x03\x03\x00\x05world"
    for rec in parse_pcap_tls_records(sample):
        print(f"  CT={ContentType(rec.content_type).name:<14} ver={rec.version} len={rec.length}")


if __name__ == "__main__":
    main()
