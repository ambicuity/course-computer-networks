"""Digital Video: raw bitrate, frame sizes, JPEG/MPEG mechanics.

A stdlib-only demonstration that computes uncompressed video bitrates
for common resolutions, shows the compression ratio required to hit
target streaming rates, simulates the JPEG 8x8 block decomposition
and a DCT/quantization round-trip, and prints an MPEG frame-type
reference table.

Run:  python3 main.py
Exit: 0
"""

from __future__ import annotations

import math
from typing import List, Tuple


# ---- Raw bitrate ----------------------------------------------------------

def raw_bitrate_bps(width: int, height: int, bits_per_pixel: int, fps: float) -> float:
    """Uncompressed video bitrate in bits per second."""
    return width * height * bits_per_pixel * fps


def bitrate_table() -> None:
    """Print raw bitrates and compression ratios for common resolutions."""
    print("=== Uncompressed video bitrate (24 bits/pixel) ===")
    cases = [
        ("320x240 (low-res)", 320, 240, 30),
        ("640x480 (NTSC)", 640, 480, 30),
        ("720x480 (DVD)", 720, 480, 29.97),
        ("1280x720 (HDTV)", 1280, 720, 30),
        ("1920x1080 (Full HD)", 1920, 1080, 30),
    ]
    targets = [1_500_000, 512_000, 8_000_000]  # 1.5 Mbps, 512 kbps, 8 Mbps
    print(f"{'resolution':>22} {'fps':>6} {'raw Mbps':>10} ", end="")
    for t in targets:
        print(f"{t/1e6:>10.2f}M ratio", end="")
    print()
    for name, w, h, fps in cases:
        raw = raw_bitrate_bps(w, h, 24, fps)
        print(f"{name:>22} {fps:>6.2f} {raw/1e6:>10.2f} ", end="")
        for t in targets:
            ratio = raw / t
            print(f"{ratio:>13.1f}:1", end="")
        print()
    print()


# ---- JPEG block decomposition --------------------------------------------

def count_jpeg_blocks(width: int, height: int) -> Tuple[int, int, int]:
    """Return (Y blocks, Cb blocks, Cr blocks) after 4:2:0 chroma subsampling."""
    y_blocks = (width // 8) * (height // 8)
    # 4:2:0 halves chroma in both dimensions
    cb_w, cb_h = width // 2, height // 2
    cb_blocks = (cb_w // 8) * (cb_h // 8)
    return y_blocks, cb_blocks, cb_blocks


def jpeg_block_demo() -> None:
    """Print block counts for a 640x480 frame."""
    print("=== JPEG block decomposition (640x480, 4:2:0) ===")
    y, cb, cr = count_jpeg_blocks(640, 480)
    total = y + cb + cr
    print(f"  Y  blocks: {y}  (640x480 -> 80x60 = 4800 blocks of 8x8)")
    print(f"  Cb blocks: {cb} (320x240 -> 40x30 = 1200 blocks)")
    print(f"  Cr blocks: {cr}")
    print(f"  total     : {total} blocks per frame")
    print()


# ---- DCT + quantization demo ---------------------------------------------

def dct_1d(block: List[float]) -> List[float]:
    """Naive 1D DCT-II of an 8-element block (for demo only)."""
    N = len(block)
    out = [0.0] * N
    for k in range(N):
        s = 0.0
        for n in range(N):
            s += block[n] * math.cos(math.pi * (n + 0.5) * k / N)
        out[k] = s * math.sqrt(2.0 / N) if k > 0 else s / math.sqrt(N)
    return out


def dct_8x8(block: List[List[float]]) -> List[List[float]]:
    """Naive 2D DCT-II on an 8x8 block (row then column)."""
    rows = [dct_1d(r) for r in block]
    cols: List[List[float]] = [[0.0] * 8 for _ in range(8)]
    for c in range(8):
        col_in = [rows[r][c] for r in range(8)]
        col_out = dct_1d(col_in)
        for r in range(8):
            cols[r][c] = col_out[r]
    return cols


def quantize(coeff: List[List[float]], qtable: List[List[int]]) -> List[List[int]]:
    """Round-divide coefficients by the quantization table."""
    return [[int(round(coeff[r][c] / qtable[r][c])) for c in range(8)] for r in range(8)]


def zigzag_scan(matrix: List[List[int]]) -> List[int]:
    """Flatten an 8x8 matrix in JPEG zigzag order."""
    order = [
        (0,0),(0,1),(1,0),(2,0),(1,1),(0,2),(0,3),(1,2),
        (2,1),(3,0),(4,0),(3,1),(2,2),(1,3),(0,4),(0,5),
        (1,4),(2,3),(3,2),(4,1),(5,0),(6,0),(5,1),(4,2),
        (3,3),(2,4),(1,5),(0,6),(0,7),(1,6),(2,5),(3,4),
        (4,3),(5,2),(6,1),(7,0),(7,1),(6,2),(5,3),(4,4),
        (3,5),(2,6),(1,7),(2,7),(3,6),(4,5),(5,4),(6,3),
        (7,2),(7,3),(6,4),(5,5),(4,6),(3,7),(4,7),(5,6),
        (6,5),(7,4),(7,5),(6,6),(5,7),(6,7),(7,6),(7,7),
    ]
    return [matrix[r][c] for (r, c) in order]


def run_length_encode(seq: List[int]) -> List[Tuple[int, int]]:
    """Run-length encode a zigzag sequence as (value, run) pairs."""
    out: List[Tuple[int, int]] = []
    i = 0
    while i < len(seq):
        v = seq[i]
        run = 1
        while i + run < len(seq) and seq[i + run] == v:
            run += 1
        out.append((v, run))
        i += run
    return out


def jpeg_pipeline_demo() -> None:
    """Run an 8x8 luminance block through DCT, quantization, zigzag, RLE."""
    print("=== JPEG pipeline on one 8x8 block (luminance) ===")
    # a smooth gradient block centered around 128
    block = [[128.0 + (r - 3.5) * 4 + (c - 3.5) * 4 for c in range(8)] for r in range(8)]
    print("  input block (sample values):")
    for r in block:
        print("   " + " ".join(f"{v:6.1f}" for v in r))
    coeffs = dct_8x8(block)
    # standard-ish quantization table (sharply rising)
    q = [
        [16,11,10,16,24,40,51,61],
        [12,12,14,19,26,58,60,55],
        [14,13,16,24,40,57,69,56],
        [14,17,22,29,51,87,80,62],
        [18,22,37,56,68,109,103,77],
        [24,35,55,64,81,104,113,92],
        [49,64,78,87,103,121,120,101],
        [72,92,95,98,112,100,103,99],
    ]
    qcoeff = quantize(coeffs, q)
    print("  quantized DCT coefficients (8x8):")
    for row in qcoeff:
        print("   " + " ".join(f"{v:4d}" for v in row))
    zig = zigzag_scan(qcoeff)
    rle = run_length_encode(zig)
    print(f"  zigzag RLE: {rle[:8]}{' ...' if len(rle) > 8 else ''}")
    nonzero = sum(1 for v in zig if v != 0)
    print(f"  non-zero coefficients: {nonzero}/64  (high-freq dropped by quantization)")
    print()


# ---- MPEG frame types ----------------------------------------------------

def mpeg_frame_table() -> None:
    """Print the MPEG I/P/B frame reference table."""
    print("=== MPEG frame types ===")
    rows = [
        ("I-frame", "self-contained", "none", "random access, error recovery, multicast join"),
        ("P-frame", "predictive", "previous I/P", "macroblock diff + motion vector"),
        ("B-frame", "bidirectional", "past + future I/P", "best compression; needs buffering"),
    ]
    print(f"{'type':>10} {'kind':>15} {'references':>18} {'use':>40}")
    for t, k, ref, u in rows:
        print(f"{t:>10} {k:>15} {ref:>18} {u:>40}")
    print()


def mpeg_standards_table() -> None:
    """Print MPEG standards timeline."""
    print("=== MPEG standards ===")
    rows = [
        ("MPEG-1", 1993, "~1 Mbps (VCR)", "40:1"),
        ("MPEG-2", 1996, "4-8 Mbps (DVD/DVB)", "varies"),
        ("MPEG-4 obj", 1999, "natural + synthetic", "varies"),
        ("AVC/H.264", 2003, "Blu-ray HDTV", ">50:1"),
    ]
    print(f"{'standard':>12} {'year':>6} {'target':>22} {'ratio':>10}")
    for s, y, t, r in rows:
        print(f"{s:>12} {y:>6} {t:>22} {r:>10}")
    print()


def main() -> None:
    print("Digital Video — bitrate, JPEG, MPEG\n")
    bitrate_table()
    jpeg_block_demo()
    jpeg_pipeline_demo()
    mpeg_frame_table()
    mpeg_standards_table()
    print("Done. All demonstrations completed.")


if __name__ == "__main__":
    main()
