"""TLS 1.3 ClientHello parser and key-schedule label demo.

Stdlib-only. Parses a hex-encoded TLS 1.3 ClientHello record, walks the
record layer, Handshake header, legacy fields, cipher suite list, and every
extension; then demonstrates the HKDF-Expand-Label framing that RFC 8446
section 7.1 pins byte-for-byte (without performing real X25519 math, which
would require the cryptography package).

Run:  python3 main.py
"""

from __future__ import annotations

import hashlib
import hmac
import struct
from dataclasses import dataclass, field
from typing import List, Tuple

# --- IANA registries (small slices relevant to TLS 1.3) ----------------------

CIPHER_SUITES = {
    0x1301: "TLS_AES_128_GCM_SHA256",
    0x1302: "TLS_AES_256_GCM_SHA384",
    0x1303: "TLS_CHACHA20_POLY1305_SHA256",
    0x1304: "TLS_AES_128_CCM_SHA256",
    0x1305: "TLS_AES_128_CCM_8_SHA256",
}

NAMED_GROUPS = {
    0x0017: "secp256r1",
    0x0018: "secp384r1",
    0x0019: "secp521r1",
    0x001D: "x25519",
    0x001E: "x448",
}

SIG_ALGS = {
    0x0403: "ecdsa_secp256r1_sha256",
    0x0503: "ecdsa_secp384r1_sha384",
    0x0603: "ecdsa_secp521r1_sha512",
    0x0807: "ed25519",
    0x0808: "ed448",
    0x0804: "rsa_pss_rsae_sha256",
    0x0805: "rsa_pss_rsae_sha384",
    0x0806: "rsa_pss_rsae_sha512",
    0x0401: "rsa_pkcs1_sha256",
    0x0501: "rsa_pkcs1_sha384",
}

EXT_TYPES = {
    0x0000: "server_name",
    0x000A: "supported_groups",
    0x000B: "ec_point_formats",
    0x000D: "signature_algorithms",
    0x0010: "application_layer_protocol_negotiation",
    0x002B: "supported_versions",
    0x002D: "psk_key_exchange_modes",
    0x0033: "key_share",
    0x0029: "pre_shared_key",
    0x0017: "extended_master_secret",
}

CONTENT_HANDSHAKE = 22


# --- A synthetic but well-formed TLS 1.3 ClientHello --------------------------
# Built bottom-up so every length field is correct. record header wraps a
# Handshake (type=1) whose payload is: legacy_version 0x0303 | 32-byte random |
# session_id (len 0) | cipher_suites (4 suites) | compression (1 method: null)
# | extensions block.

def _u24(n: int) -> bytes:
    return bytes([(n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF])


def _build_client_hello_hex() -> str:
    client_random = b"\x01" * 32
    cipher_suites = struct.pack(">HHHH", 0x1301, 0x1302, 0x1303, 0x1304)

    def ext(etype: int, payload: bytes) -> bytes:
        return struct.pack(">HH", etype, len(payload)) + payload

    # key_share: client form is u16 list_len, then entries (group, klen, key).
    ks_entry = struct.pack(">HH", 0x0017, 32) + b"\x02" * 32  # secp256r1, 32-byte key
    ks_entry += struct.pack(">HH", 0x001D, 32) + b"\x03" * 32  # x25519, 32-byte key
    key_share = ext(0x0033, struct.pack(">H", len(ks_entry)) + ks_entry)

    supported_versions = ext(0x002B, bytes([4]) + struct.pack(">HH", 0x0304, 0x0303))
    supported_groups = ext(0x000A, struct.pack(">H", 6) + struct.pack(">HHH", 0x001D, 0x0017, 0x0018))
    sig_list = struct.pack(">HHHHHHH", 0x0403, 0x0804, 0x0401, 0x0503, 0x0805, 0x0501, 0x0807)
    sig_algs = ext(0x000D, struct.pack(">H", len(sig_list)) + sig_list)
    alpn = ext(0x0010, struct.pack(">H", 12) + bytes([2]) + b"h2" + bytes([8]) + b"http/1.1")
    server_name = ext(0x0000, struct.pack(">H", 16) + bytes([0, 0]) + struct.pack(">H", 0x17) + b"example.com")
    psk_kem = ext(0x002D, bytes([1, 1]))

    extensions = key_share + supported_versions + supported_groups + sig_algs + alpn + server_name + psk_kem

    ch_body = (
        struct.pack(">H", 0x0303)  # legacy_version
        + client_random
        + bytes([0])               # session_id length 0
        + struct.pack(">H", len(cipher_suites)) + cipher_suites
        + bytes([1, 0])            # compression: 1 method, null
        + struct.pack(">H", len(extensions)) + extensions
    )
    handshake = bytes([1]) + _u24(len(ch_body)) + ch_body
    record = struct.pack(">BHH", CONTENT_HANDSHAKE, 0x0303, len(handshake)) + handshake
    return record.hex()


CLIENT_HELLO_HEX = _build_client_hello_hex()


@dataclass
class Extension:
    etype: int
    name: str
    raw: bytes


@dataclass
class ClientHello:
    record_version: Tuple[int, int]
    handshake_len: int
    legacy_version: Tuple[int, int]
    random: bytes
    session_id: bytes
    cipher_suites: List[int]
    extensions: List[Extension] = field(default_factory=list)

    # derived views
    supported_versions: List[int] = field(default_factory=list)
    supported_groups: List[int] = field(default_factory=list)
    sig_algs: List[int] = field(default_factory=list)
    key_share_groups: List[int] = field(default_factory=list)


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def take(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise ValueError(f"short read: want {n} at {self.pos}, have {len(self.data)}")
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out

    def u8(self) -> int:
        return self.take(1)[0]

    def u16(self) -> int:
        return struct.unpack(">H", self.take(2))[0]

    def u24(self) -> int:
        b = self.take(3)
        return (b[0] << 16) | (b[1] << 8) | b[2]

    def remaining(self) -> int:
        return len(self.data) - self.pos


def parse_client_hello(hex_blob: str) -> ClientHello:
    data = bytes.fromhex(hex_blob)
    r = Reader(data)

    content_type = r.u8()
    if content_type != CONTENT_HANDSHAKE:
        raise ValueError(f"expected handshake record (22), got {content_type}")
    rec_major, rec_minor = r.u8(), r.u8()
    rec_len = r.u16()

    body = Reader(r.take(rec_len))
    hs_type = body.u8()
    if hs_type != 1:
        raise ValueError(f"expected ClientHello (1), got {hs_type}")
    hs_len = body.u24()
    leg_major, leg_minor = body.u8(), body.u8()
    rand = body.take(32)
    sid_len = body.u8()
    sid = body.take(sid_len)
    cs_len = body.u16()
    suites: List[int] = []
    for _ in range(cs_len // 2):
        suites.append(body.u16())
    comp_len = body.u8()
    body.take(comp_len)  # discard; always [0] in 1.3

    ext_len = body.u16()
    ch = ClientHello(
        record_version=(rec_major, rec_minor),
        handshake_len=hs_len,
        legacy_version=(leg_major, leg_minor),
        random=rand,
        session_id=sid,
        cipher_suites=suites,
    )
    ext_end = body.pos + ext_len
    while body.pos < ext_end:
        etype = body.u16()
        elen = body.u16()
        eraw = body.take(elen)
        ch.extensions.append(
            Extension(etype, EXT_TYPES.get(etype, f"unknown(0x{etype:04x})"), eraw)
        )
        _parse_extension_payload(ch, etype, eraw)
    return ch


def _parse_extension_payload(ch: ClientHello, etype: int, raw: bytes) -> None:
    r = Reader(raw)
    if etype == 0x002B:  # supported_versions (client form)
        list_len = r.u8()
        for _ in range(list_len // 2):
            ch.supported_versions.append(r.u16())
    elif etype == 0x000A:  # supported_groups
        list_len = r.u16()
        for _ in range(list_len // 2):
            ch.supported_groups.append(r.u16())
    elif etype == 0x000D:  # signature_algorithms
        list_len = r.u16()
        for _ in range(list_len // 2):
            ch.sig_algs.append(r.u16())
    elif etype == 0x0033:  # key_share (client form)
        ks_len = r.u16()
        end = r.pos + ks_len
        while r.pos < end:
            group = r.u16()
            klen = r.u16()
            r.take(klen)
            ch.key_share_groups.append(group)


# --- RFC 8446 section 7.1 HKDF-Expand-Label framing ---------------------------

def hkdf_expand_label(
    secret: bytes, label: str, context: bytes, length: int, hash_fn=hashlib.sha256
) -> bytes:
    """Frame HKDF-Expand-Label exactly as TLS 1.3 does, then run HKDF-Expand.

    HkdfLabel struct:
      length (u16) | label_length (u8) | "tls13 "+label | context_length (u8) | context
    HKDF-Expand is HMAC-Hash with counter t=1 (one block is enough here).
    """
    full_label = b"tls13 " + label.encode("ascii")
    info = (
        struct.pack(">H", length)
        + bytes([len(full_label)]) + full_label
        + bytes([len(context)]) + context
    )
    prk = secret
    t1 = hmac.new(prk, info + b"\x01", hash_fn).digest()
    return t1[:length]


def demo_key_schedule_labels() -> None:
    print("\n--- Key schedule label framing (RFC 8446 section 7.1) ---")
    early_secret = hashlib.sha256(b"demo-psk-or-zero").digest()
    for label in ["derived", "c hs traffic", "b hs traffic", "c ap traffic", "b ap traffic"]:
        out = hkdf_expand_label(early_secret, label, b"", 32)
        print(f"  HKDF-Expand-Label({label!r:18}) -> {out.hex()[:32]}...")


def main() -> None:
    ch = parse_client_hello(CLIENT_HELLO_HEX)
    print("=== TLS 1.3 ClientHello dissection ===")
    rec_body_len = len(bytes.fromhex(CLIENT_HELLO_HEX)) - 5
    print(
        f"Record: ContentType=22 (Handshake)  version=0x"
        f"{ch.record_version[0]:02x}{ch.record_version[1]:02x}  body_len=0x{rec_body_len:x}"
    )
    print(f"Handshake: type=1 (ClientHello)  length={ch.handshake_len}")
    print(
        f"legacy_version=0x{ch.legacy_version[0]:02x}{ch.legacy_version[1]:02x} "
        "(ignored; real version is in supported_versions)"
    )
    print(f"random={ch.random.hex()[:32]}...")
    print("session_id=<empty> (middlebox-compat only)")
    print("\nCipher suites offered:")
    for s in ch.cipher_suites:
        marker = "  <-- TLS 1.3" if s in CIPHER_SUITES else "  (non-1.3)"
        print(f"  0x{s:04x}  {CIPHER_SUITES.get(s, 'unknown')}{marker}")

    print("\nsupported_versions extension:")
    for v in ch.supported_versions:
        name = {0x0304: "TLS 1.3", 0x0303: "TLS 1.2", 0x0302: "TLS 1.1"}.get(v, "other")
        print(f"  0x{v:04x}  {name}")

    print("\nsupported_groups extension:")
    for g in ch.supported_groups:
        print(f"  0x{g:04x}  {NAMED_GROUPS.get(g, 'unknown')}")

    print("\nkey_share (pre-loaded ephemeral groups):")
    for g in ch.key_share_groups:
        print(f"  0x{g:04x}  {NAMED_GROUPS.get(g, 'unknown')}")

    print("\nsignature_algorithms extension:")
    for a in ch.sig_algs:
        print(f"  0x{a:04x}  {SIG_ALGS.get(a, 'unknown')}")

    print("\nAll extensions in order:")
    for e in ch.extensions:
        print(f"  0x{e.etype:04x}  {e.name:32}  {len(e.raw)} bytes")

    chosen_suite = next((s for s in ch.cipher_suites if s in CIPHER_SUITES), None)
    chosen_group = next((g for g in ch.supported_groups if g in ch.key_share_groups), None)
    chosen_sig = ch.sig_algs[0] if ch.sig_algs else None
    print("\n=== Predicted server choice (first-intersect heuristic) ===")
    print(f"  cipher_suite : 0x{chosen_suite:04x}  {CIPHER_SUITES.get(chosen_suite)}")
    print(f"  named_group  : 0x{chosen_group:04x}  {NAMED_GROUPS.get(chosen_group)}")
    print(f"  signature_alg: 0x{chosen_sig:04x}  {SIG_ALGS.get(chosen_sig)}")
    print("  -> if any is None, the server sends Alert handshake_failure (40).")

    demo_key_schedule_labels()


if __name__ == "__main__":
    main()
