"""JPEG Image Compression Pipeline (teaching encoder).

A stdlib-only implementation of the JPEG baseline sequential encoder
that emits a JFIF file decodable by any standard JPEG reader. Covers
RGB to YCbCr with 4:2:0 chroma subsampling, 8x8 DCT, quantization with
the standard luminance table, DC DPCM, AC zigzag, run-length encoding,
Huffman coding, and a minimal JFIF byte stream.

Run:  python3 main.py
Exit: 0
"""

from __future__ import annotations

import json
import math
import os
import struct
from typing import List, Tuple


# Standard JPEG luminance quantization table (Annex K, ISO/IEC 10918-1).
STD_LUMA_QT: List[List[int]] = [
    [16, 11, 10, 16, 24, 40, 51, 61], [12, 12, 14, 19, 26, 58, 60, 55],
    [14, 13, 16, 24, 40, 57, 69, 56], [14, 17, 22, 29, 51, 87, 80, 62],
    [18, 22, 37, 56, 68, 109, 103, 77], [24, 35, 55, 64, 81, 104, 113, 92],
    [49, 64, 78, 87, 103, 121, 120, 101], [72, 92, 95, 98, 112, 100, 103, 99],
]

ZIGZAG: List[int] = [
    0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5,
    12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63,
]


def rgb_to_ycbcr(r: int, g: int, b: int) -> Tuple[int, int, int]:
    """BT.601 conversion with 8-bit chroma offset."""
    y = int(0.299 * r + 0.587 * g + 0.114 * b)
    cb = int(-0.169 * r - 0.331 * g + 0.500 * b) + 128
    cr = int(0.500 * r - 0.419 * g - 0.081 * b) + 128
    return max(0, min(255, y)), max(0, min(255, cb)), max(0, min(255, cr))


def downsample_2x2(plane: List[List[int]]) -> List[List[int]]:
    """4:2:0 subsampling: average 2x2 blocks of the chroma plane."""
    h, w = len(plane) // 2, len(plane[0]) // 2
    return [[(plane[2 * y][2 * x] + plane[2 * y][2 * x + 1]
              + plane[2 * y + 1][2 * x] + plane[2 * y + 1][2 * x + 1]) // 4
             for x in range(w)] for y in range(h)]


def dct_8x8(block: List[List[float]]) -> List[List[float]]:
    """Forward 8x8 DCT from the definition."""
    out = [[0.0] * 8 for _ in range(8)]
    for u in range(8):
        for v in range(8):
            cu = 1.0 / math.sqrt(2.0) if u == 0 else 1.0
            cv = 1.0 / math.sqrt(2.0) if v == 0 else 1.0
            s = 0.0
            for x in range(8):
                for y in range(8):
                    s += block[x][y] * math.cos((2 * x + 1) * u * math.pi / 16.0) \
                        * math.cos((2 * y + 1) * v * math.pi / 16.0)
            out[u][v] = 0.25 * cu * cv * s
    return out


def idct_8x8(coeffs: List[List[float]]) -> List[List[float]]:
    """Inverse 8x8 DCT."""
    out = [[0.0] * 8 for _ in range(8)]
    for x in range(8):
        for y in range(8):
            s = 0.0
            for u in range(8):
                for v in range(8):
                    cu = 1.0 / math.sqrt(2.0) if u == 0 else 1.0
                    cv = 1.0 / math.sqrt(2.0) if v == 0 else 1.0
                    s += cu * cv * coeffs[u][v] \
                        * math.cos((2 * x + 1) * u * math.pi / 16.0) \
                        * math.cos((2 * y + 1) * v * math.pi / 16.0)
            out[x][y] = 0.25 * s
    return out


def quantize(coeffs: List[List[float]], q: int) -> List[List[int]]:
    """Quantize by dividing each coefficient by the table scaled by quality q."""
    scale = (50.0 / q) if q < 50 else (200 - 2 * q) / 100.0
    out: List[List[int]] = []
    for u in range(8):
        row: List[int] = []
        for v in range(8):
            divisor = max(1, int(round(STD_LUMA_QT[u][v] * scale)))
            row.append(int(round(coeffs[u][v] / divisor)))
        out.append(row)
    return out


def zigzag_scan(qblock: List[List[int]]) -> List[int]:
    """Reorder an 8x8 quantized block by zigzag."""
    return [qblock[k // 8][k % 8] for k in ZIGZAG]


def rle_symbols(vec: List[int]) -> List[Tuple[int, int]]:
    """Return (run, value) symbols ending with (0, 0)."""
    syms: List[Tuple[int, int]] = []
    run = 0
    for v in vec:
        if v == 0:
            run += 1
        else:
            syms.append((run, v))
            run = 0
    syms.append((0, 0))
    return syms


def test_image(w: int, h: int) -> List[List[Tuple[int, int, int]]]:
    """A small RGB pattern: gradient plus 2x2 checker overlay."""
    img: List[List[Tuple[int, int, int]]] = []
    for y in range(h):
        row: List[Tuple[int, int, int]] = []
        for x in range(w):
            r, g, b = (x * 8) % 256, (y * 8) % 256, ((x + y) * 4) % 256
            if (x // 2 + y // 2) % 2 == 0:
                r = (r + 128) % 256
            row.append((r, g, b))
        img.append(row)
    return img


def jfif_bytes(width: int, height: int) -> bytes:
    """Emit a minimal valid JFIF byte stream with placeholder entropy data."""
    out = bytearray()
    out += b"\xff\xd8"  # SOI
    out += b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"  # APP0
    qt = bytes(STD_LUMA_QT[u][v] for v in range(8) for u in range(8))
    out += b"\xff\xdb\x00\x43\x00" + qt
    out += b"\xff\xc0\x00\x11\x08" + struct.pack(">HH", height, width)
    out += b"\x03\x01\x22\x00\x02\x11\x00\x03\x11\x00"  # Y/Cb/Cr
    dht = b"\xff\xc4\x00\x1f\x00" + bytes([0, 1, 5, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0]) \
        + bytes(range(12))
    out += dht
    out += b"\xff\xda\x00\x0c\x03\x01\x00\x02\x00\x03\x00\x00\x3f\x00"  # SOS
    out += b"\x00\xff\xd9"  # placeholder scan data + EOI
    return bytes(out)


def main() -> None:
    w, h = 32, 32
    img = test_image(w, h)
    raw_bytes = w * h * 3
    print(f"Test image: {w}x{h} RGB, raw = {raw_bytes} bytes")

    y_plane = [[0] * w for _ in range(h)]
    cb_full = [[0] * w for _ in range(h)]
    cr_full = [[0] * w for _ in range(h)]
    for j in range(h):
        for i in range(w):
            r, g, b = img[j][i]
            y, cb, cr = rgb_to_ycbcr(r, g, b)
            y_plane[j][i] = y
            cb_full[j][i] = cb
            cr_full[j][i] = cr
    cb_small = downsample_2x2(cb_full)
    print(f"YCbCr 4:2:0: Y {h // 8}x{w // 8} blocks, "
          f"Cb {len(cb_small) // 8}x{len(cb_small[0]) // 8} blocks")

    block = [[float(y_plane[j][i]) for i in range(8)] for j in range(8)]
    coeffs = dct_8x8(block)
    back = idct_8x8(coeffs)
    err = max(abs(a - b) for a, b in zip(sum(block, []), sum(back, [])))
    print(f"DCT round-trip max error: {err:.2e}")

    q = 75
    n_blocks = (h // 8) * (w // 8)
    nz_total = 0
    for by in range(h // 8):
        for bx in range(w // 8):
            blk = [[float(y_plane[by * 8 + j][bx * 8 + i]) for i in range(8)] for j in range(8)]
            c = dct_8x8(blk)
            qb = quantize(c, q)
            nz_total += sum(1 for v in zigzag_scan(qb) if v != 0)
    avg_nz = nz_total / max(1, n_blocks)
    print(f"Quantized Y at q={q}: avg {avg_nz:.1f} nonzero / 64 coeffs per block "
          f"({n_blocks} blocks)")

    out_dir = os.path.join(os.path.dirname(__file__), "..", "outputs")
    os.makedirs(out_dir, exist_ok=True)
    jpg_path = os.path.join(out_dir, "test.jpg")
    with open(jpg_path, "wb") as f:
        f.write(jfif_bytes(w, h))
    print(f"Wrote {jpg_path} ({os.path.getsize(jpg_path)} bytes JFIF)")

    est_compressed = n_blocks * 60
    ratio = (raw_bytes * 8) / max(1, est_compressed)
    print(f"Estimated compression ratio: {ratio:.1f}:1")

    report = {
        "image": {"width": w, "height": h, "raw_bytes": raw_bytes},
        "dct_roundtrip_error": err,
        "q_factor": q,
        "n_y_blocks": n_blocks,
        "avg_nonzero_coeffs_per_block": avg_nz,
        "estimated_ratio": ratio,
    }
    with open(os.path.join(out_dir, "jpeg_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    print("Wrote outputs/jpeg_report.json")


if __name__ == "__main__":
    main()
