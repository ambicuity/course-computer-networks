#!/usr/bin/env python3
"""MIME encoder/decoder: base64, quoted-printable, multipart/* tree builder.

Implements the wire formats from RFC 2045, RFC 2046, and RFC 4648. Builds a
multipart/mixed envelope with an inline text/plain part and an attached
application/pdf stub encoded in base64, then walks the resulting tree.

Run with `python3 main.py`.
"""

from __future__ import annotations

import base64
import binascii
import quopri
import secrets
from dataclasses import dataclass, field
from typing import Dict, List, Optional


B64_ALPHA = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def b64_encode(data: bytes) -> str:
    """RFC 4648 §4 base64 encoder, stdlib-free."""
    out = bytearray()
    n = len(data)
    i = 0
    while i + 3 <= n:
        b0, b1, b2 = data[i], data[i + 1], data[i + 2]
        out.append(B64_ALPHA[b0 >> 2])
        out.append(B64_ALPHA[((b0 & 0x03) << 4) | (b1 >> 4)])
        out.append(B64_ALPHA[((b1 & 0x0F) << 2) | (b2 >> 6)])
        out.append(B64_ALPHA[b2 & 0x3F])
        i += 3
    rem = n - i
    if rem == 1:
        b0 = data[i]
        out.append(B64_ALPHA[b0 >> 2])
        out.append(B64_ALPHA[(b0 & 0x03) << 4])
        out.append(b"=")
        out.append(b"=")
    elif rem == 2:
        b0, b1 = data[i], data[i + 1]
        out.append(B64_ALPHA[b0 >> 2])
        out.append(B64_ALPHA[((b0 & 0x03) << 4) | (b1 >> 4)])
        out.append(B64_ALPHA[(b1 & 0x0F) << 2])
        out.append(b"=")
    return bytes(out).decode("ascii")


def b64_decode(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def qp_encode(text: str) -> bytes:
    """Use stdlib quopri; mimics RFC 2045 §6.7 (line limit 76, soft break =\\r\\n)."""
    return quopri.encodestring(text.encode("utf-8"))


def qp_decode(blob: bytes) -> str:
    return quopri.decodestring(blob).decode("utf-8")


def random_boundary() -> str:
    return secrets.token_hex(12)


@dataclass
class MimePart:
    headers: Dict[str, str]
    body: bytes
    children: List["MimePart"] = field(default_factory=list)


def build_multipart(parent_type: str, parts: List[MimePart], boundary: Optional[str] = None) -> MimePart:
    boundary = boundary or random_boundary()
    body = bytearray()
    for part in parts:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(_render_headers(part.headers).encode())
        body.extend(b"\r\n")
        body.extend(part.body)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return MimePart(
        headers={
            "Content-Type": f'{parent_type}; boundary="{boundary}"',
        },
        body=bytes(body),
        children=parts,
    )


def _render_headers(headers: Dict[str, str]) -> str:
    return "\r\n".join(f"{k}: {v}" for k, v in headers.items())


def walk_parts(part: MimePart, depth: int = 0) -> List[str]:
    indent = "  " * depth
    head = part.headers.get("Content-Type", "<none>")
    lines = [f"{indent}part: {head}  bytes={len(part.body)}"]
    for child in part.children:
        lines.extend(walk_parts(child, depth + 1))
    return lines


SAMPLE_PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"


def main() -> None:
    print("=" * 64)
    print("MIME  --  RFC 2045 / 2046 / 4648")
    print("=" * 64)

    print("\nBase64 round-trip:")
    for raw in (b"hi?", b"hi", b"h", b"hello"):
        encoded = b64_encode(raw)
        decoded = b64_decode(encoded)
        print(f"  {raw!r:<10}  ->  {encoded:<12}  ({len(encoded)} chars)  ->  {decoded!r}")

    cross = base64.b64encode(raw).decode("ascii")
    if cross != encoded:
        raise AssertionError("stdlib disagreement!")

    print("\nQuoted-printable (UTF-8 'café'):")
    qp = qp_encode("café")
    print(f"  encoded: {qp}")
    print(f"  decoded: {qp_decode(qp)}")

    print("\nmultipart/mixed envelope:")
    text_part = MimePart(
        headers={
            "Content-Type": 'text/plain; charset="UTF-8"',
            "Content-Transfer-Encoding": "7bit",
        },
        body=b"Here is the invoice you asked for.\r\n",
    )
    pdf_part = MimePart(
        headers={
            "Content-Type": 'application/pdf; name="invoice.pdf"',
            "Content-Transfer-Encoding": "base64",
            "Content-Disposition": 'attachment; filename="invoice.pdf"',
        },
        body=b64_encode(SAMPLE_PDF).encode("ascii"),
    )
    envelope = build_multipart("multipart/mixed", [text_part, pdf_part])
    print(_render_headers(envelope.headers))
    print()
    print(envelope.body.decode("ascii"))

    print("\nTree walk:")
    for line in walk_parts(envelope):
        print(f"  {line}")


if __name__ == "__main__":
    main()
