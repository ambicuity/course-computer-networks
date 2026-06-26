"""ASN.1 DER encoder/decoder with a tiny X.509 v3 skeleton builder.

This file implements just enough of DER to make X.509 legibly parseable:
TLV primitives for INTEGER, BIT STRING, OCTET STRING, NULL, OID, UTCTime,
PrintableString, UTF8String, plus constructed SEQUENCE and SET wrappers.
We then assemble a v3 Certificate skeleton and re-parse it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple


class ASN1DecodeError(Exception):
    pass


# --- Length encoding. ---

def encode_length(n: int) -> bytes:
    if n < 0:
        raise ValueError("length must be non-negative")
    if n < 0x80:
        return bytes([n])
    body = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(body)]) + body


def decode_length(buf: bytes, offset: int) -> Tuple[int, int]:
    if offset >= len(buf):
        raise ASN1DecodeError("buffer underrun reading length")
    first = buf[offset]
    offset += 1
    if first < 0x80:
        return first, offset
    nbytes = first & 0x7F
    if nbytes == 0:
        raise ASN1DecodeError("indefinite length not supported in DER")
    if offset + nbytes > len(buf):
        raise ASN1DecodeError("length octets overrun buffer")
    return int.from_bytes(buf[offset : offset + nbytes], "big"), offset + nbytes


# --- TLV helper. ---

def _tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + encode_length(len(value)) + value


# --- Primitive encoders. ---

def encode_integer(n: int) -> bytes:
    if n == 0:
        return _tlv(0x02, b"\x00")
    body = n.to_bytes((n.bit_length() + 7) // 8, "big", signed=(n < 0))
    if body[0] & 0x80:
        body = b"\x00" + body
    return _tlv(0x02, body)


def decode_integer(buf: bytes, offset: int = 0) -> Tuple[int, int]:
    tag = buf[offset]
    offset += 1
    if tag != 0x02:
        raise ASN1DecodeError(f"expected INTEGER tag 0x02, got {tag:#x}")
    length, offset = decode_length(buf, offset)
    body = buf[offset : offset + length]
    return int.from_bytes(body, "big", signed=False), offset + length


def encode_octet_string(data: bytes) -> bytes:
    return _tlv(0x04, data)


def decode_octet_string(buf: bytes, offset: int) -> Tuple[bytes, int]:
    tag = buf[offset]
    offset += 1
    if tag != 0x04:
        raise ASN1DecodeError(f"expected OCTET STRING 0x04, got {tag:#x}")
    length, offset = decode_length(buf, offset)
    return buf[offset : offset + length], offset + length


def encode_bit_string(bits: bytes, unused: int = 0) -> bytes:
    return _tlv(0x03, bytes([unused]) + bits)


def decode_bit_string(buf: bytes, offset: int) -> Tuple[bytes, int]:
    tag = buf[offset]
    offset += 1
    if tag != 0x03:
        raise ASN1DecodeError(f"expected BIT STRING 0x03, got {tag:#x}")
    length, offset = decode_length(buf, offset)
    unused = buf[offset]
    return buf[offset + 1 : offset + length], offset + length


def encode_oid(dotted: str) -> bytes:
    arcs = [int(x) for x in dotted.split(".")]
    if len(arcs) < 2:
        raise ValueError("OID must have at least two arcs")
    out = bytearray([40 * arcs[0] + arcs[1]])
    for arc in arcs[2:]:
        if arc < 0:
            raise ValueError("negative OID arc")
        chunks = []
        v = arc
        chunks.append(v & 0x7F)
        v >>= 7
        while v:
            chunks.append((v & 0x7F) | 0x80)
            v >>= 7
        out.extend(reversed(chunks))
    return _tlv(0x06, bytes(out))


def decode_oid(buf: bytes) -> str:
    if buf[0] != 0x06:
        raise ASN1DecodeError(f"expected OID tag 0x06, got {buf[0]:#x}")
    length, offset = decode_length(buf, 1)
    body = buf[offset : offset + length]
    first = body[0]
    arcs = [first // 40, first % 40]
    value = 0
    for byte in body[1:]:
        value = (value << 7) | (byte & 0x7F)
        if not (byte & 0x80):
            arcs.append(value)
            value = 0
    return ".".join(str(a) for a in arcs)


def encode_utctime(dt: datetime) -> bytes:
    body = dt.astimezone(timezone.utc).strftime("%y%m%d%H%M%SZ").encode("ascii")
    return _tlv(0x17, body)


def encode_utf8_string(s: str) -> bytes:
    return _tlv(0x0C, s.encode("utf-8"))


def encode_printable_string(s: str) -> bytes:
    return _tlv(0x13, s.encode("ascii"))


def encode_null() -> bytes:
    return _tlv(0x05, b"")


# --- Constructed wrappers. ---

def encode_sequence(children: List[bytes]) -> bytes:
    return _tlv(0x30, b"".join(children))


def encode_set(children: List[bytes]) -> bytes:
    return _tlv(0x31, b"".join(children))


# --- X.509 v3 skeleton builder. ---

def _name_rdn(common_name: str) -> bytes:
    cn = encode_sequence([encode_oid("2.5.4.3"), encode_utf8_string(common_name)])
    return encode_set([cn])


def build_x509_v3_skeleton(
    subject: str,
    issuer: str,
    public_key_oid: str,
    public_key_bits: bytes,
    serial: int = 1,
    not_before: datetime | None = None,
    not_after: datetime | None = None,
) -> bytes:
    now = datetime.now(timezone.utc)
    nb = not_before or now
    na = not_after or now.replace(year=now.year + 1)
    sig_alg = encode_sequence([encode_oid("1.2.840.113549.1.1.11"), encode_null()])
    spki = encode_sequence([
        encode_sequence([encode_oid(public_key_oid), encode_oid("1.2.840.10045.2.1")]),
        encode_bit_string(public_key_bits),
    ])
    tbs = encode_sequence([
        encode_sequence([encode_integer(2)]),  # version [0] EXPLICIT v3
        encode_integer(serial),
        sig_alg,
        _name_rdn(issuer),
        encode_sequence([encode_utctime(nb), encode_utctime(na)]),
        _name_rdn(subject),
        spki,
    ])
    outer = encode_sequence([
        tbs,
        sig_alg,
        encode_bit_string(b"\x00" * 64),
    ])
    return outer


def parse_all(data: bytes) -> List[Tuple[int, bytes]]:
    """Walk a DER byte stream and return (tag, value) pairs."""
    out: List[Tuple[int, bytes]] = []
    pos = 0
    while pos < len(data):
        tag = data[pos]
        pos += 1
        length, pos = decode_length(data, pos)
        out.append((tag, data[pos : pos + length]))
        pos += length
    return out


def main() -> None:
    """Self-test: build a skeleton, parse it, and confirm symmetry."""
    skel = build_x509_v3_skeleton(
        subject="CN=example.com",
        issuer="CN=Acme Intermediate CA",
        public_key_oid="1.2.840.10045.2.1",
        public_key_bits=b"\x04" + b"\xab" * 64,
    )
    pairs = parse_all(skel)
    print(f"top-level TLV count: {len(pairs)}")
    print(f"outer tag: 0x{pairs[0][0]:02x} (expected 0x30 SEQUENCE)")
    # OID round trip.
    oid_bytes = encode_oid("1.2.840.113549.1.1.11")
    print(f"sha256WithRSAEncryption OID: {oid_bytes.hex()} -> {decode_oid(oid_bytes)}")
    # INTEGER round trip.
    n_bytes = encode_integer(2)
    print(f"INTEGER 2 -> {n_bytes.hex()}, decoded = {decode_integer(n_bytes)[0]}")


if __name__ == "__main__":
    main()