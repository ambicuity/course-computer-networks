"""QAM constellations and Gray coding.

Stdlib-only lab: builds Gray-coded square M-QAM constellation grids,
checks that the labeling really is Gray (adjacent points differ in one
bit), and runs a Monte-Carlo AWGN symbol-error / bit-error simulation
plus an SER-vs-SNR sweep. Run with `python3 main.py`.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Gray code
# ---------------------------------------------------------------------------
def gray_code(value: int, bits: int) -> int:
    """Return the `bits`-bit Gray code of integer `value` (g XOR (g >> 1))."""
    return (value ^ (value >> 1)) & ((1 << bits) - 1)


def gray_sequence(bits: int) -> List[int]:
    """Full reflected Gray-code sequence of length 2**bits."""
    return [gray_code(g, bits) for g in range(1 << bits)]


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


# ---------------------------------------------------------------------------
# Constellation construction
# ---------------------------------------------------------------------------
def qam_constellation(m: int, gray: bool = True) -> List[Tuple[float, float, int]]:
    """Return a square M-QAM constellation as (I, Q, label) tuples.

    Points are placed on a sqrt(M) x sqrt(M) grid centered on the origin
    with unit spacing between adjacent levels (d_min = 2). The label is
    (gray_I, gray_Q) when gray=True, else plain binary (i, q).
    """
    n = int(round(math.sqrt(m)))
    if n * n != m:
        raise ValueError(f"square QAM needs M = k^2; got {m}")
    levels = [-(n - 1) + 2 * i for i in range(n)]  # spacing of 2 -> d_min = 2
    half = n.bit_length() - 1  # bits per axis
    pts: List[Tuple[float, float, int]] = []
    for qi, q in enumerate(levels):
        for ii, i in enumerate(levels):
            hi = gray_code(ii, half) if gray else ii
            hq = gray_code(qi, half) if gray else qi
            label = (hi << half) | hq
            pts.append((float(i), float(q), label))
    return pts


def print_grid(m: int, gray: bool = True) -> None:
    """Pretty-print the constellation as a grid of label bit-strings."""
    n = int(round(math.sqrt(m)))
    half = n.bit_length() - 1
    pts = qam_constellation(m, gray)
    by_qi: Dict[int, List[int]] = {}
    for idx, (_, _, label) in enumerate(pts):
        qi = idx // n
        by_qi.setdefault(qi, []).append(label)
    label_kind = "Gray" if gray else "Binary"
    print(f"{label_kind}-labeled QAM-{m} "
          f"({half} bits per axis, {2*half} bits/symbol):")
    for qi in range(n - 1, -1, -1):
        row = " ".join(f"{v:0{2*half}b}" for v in by_qi[qi])
        print(f"  row {qi} | {row}")
    print()


def verify_gray(m: int) -> Dict[str, int]:
    """Worst-case bit distance to horizontal/vertical/diagonal neighbors."""
    n = int(round(math.sqrt(m)))
    pts = qam_constellation(m, gray=True)
    grid = {(p[0], p[1]): p[2] for p in pts}
    spacing = 2.0
    worst = {"horizontal": 0, "vertical": 0, "diagonal": 0}
    for (i, q), label in grid.items():
        for di, dq, key in [
            (spacing, 0, "horizontal"),
            (0, spacing, "vertical"),
            (spacing, spacing, "diagonal"),
        ]:
            nb = grid.get((i + di, q + dq))
            if nb is not None:
                worst[key] = max(worst[key], hamming(label, nb))
    return worst


# ---------------------------------------------------------------------------
# AWGN simulation
# ---------------------------------------------------------------------------
def _erf(x: float) -> float:
    """Abramowitz & Stegun 7.1.26 approximation of erf."""
    t = 1.0 / (1.0 + 0.3275911 * abs(x))
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t
                - 0.284496736) * t + 0.254829592) * t * math.exp(-x * x)
    return y if x >= 0 else -y


def erfc(x: float) -> float:
    return 1.0 - _erf(x)


def theoretical_ser(m: int, snr_db: float) -> float:
    """Proakis square-M-QAM SER bound: 1 - [1 - p]^2 with
    p = (1 - 1/sqrt(M)) * erfc(sqrt(3*E_s / ((M-1)*N0)))."""
    es_n0 = 10.0 ** (snr_db / 10.0)
    p = (1.0 - 1.0 / math.sqrt(m)) * erfc(math.sqrt(3.0 * es_n0 / (m - 1)))
    return 1.0 - (1.0 - p) ** 2


def simulate(m: int, snr_db: float, trials: int = 200_000,
             gray: bool = True, seed: int = 0) -> Tuple[float, float]:
    """Monte-Carlo AWGN simulation. Returns (SER, BER).

    E_s is normalized to 1, so N0 = 10**(-snr_db/10). Noise is complex
    Gaussian with variance N0/2 per real dimension.
    """
    rng = random.Random(seed)
    pts = qam_constellation(m, gray)
    es = sum(i * i + q * q for i, q, _ in pts) / m  # average symbol energy
    scale = math.sqrt(es)
    norm = [(i / scale, q / scale, lab) for i, q, lab in pts]
    n0 = 10.0 ** (-snr_db / 10.0)
    sigma = math.sqrt(n0 / 2.0)
    bits_per_sym = int(round(math.log2(m)))
    sym_errors = 0
    bit_errors = 0
    for _ in range(trials):
        i, q, sent = rng.choice(norm)
        ni = rng.gauss(0.0, sigma)
        nq = rng.gauss(0.0, sigma)
        ri, rq = i + ni, q + nq
        best = min(norm, key=lambda p: (p[0] - ri) ** 2 + (p[1] - rq) ** 2)
        if best[2] != sent:
            sym_errors += 1
            bit_errors += hamming(best[2], sent)
    ser = sym_errors / trials
    ber = bit_errors / (trials * bits_per_sym)
    return ser, ber


def sweep(m: int, snr_range: List[float], trials: int = 50_000) -> None:
    """Print simulated vs theoretical SER across an SNR range."""
    bps = int(round(math.log2(m)))
    print(f"--- M-QAM SER sweep for M={m} ({bps} bits/symbol) ---")
    print(f"{'SNR(dB)':>8} {'sim_SER':>12} {'theo_SER':>12} {'sim_BER':>12}")
    for snr in snr_range:
        ser, ber = simulate(m, snr, trials=trials, gray=True)
        theo = theoretical_ser(m, snr)
        print(f"{snr:>8.1f} {ser:>12.2e} {theo:>12.2e} {ber:>12.2e}")
    print()


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
def main() -> None:
    print("=== Gray code sequence (k=3) ===")
    print(" ".join(f"{g:03b}" for g in gray_sequence(3)))
    print()

    print("=== Gray-labeled QAM-16 grid ===")
    print_grid(16, gray=True)

    print("=== Gray verification (worst-case bit distance to neighbors) ===")
    for m in (4, 16, 64):
        w = verify_gray(m)
        ok = "OK" if (w["horizontal"] == 1 and w["vertical"] == 1) else "FAIL"
        print(f"  QAM-{m}: horiz={w['horizontal']} vert={w['vertical']} "
              f"diag={w['diagonal']}  [{ok}]")
    print()

    print("=== Single-point simulation: QAM-16 @ 14 dB ===")
    ser, ber = simulate(16, 14.0, trials=200_000)
    print(f"  sim SER = {ser:.4e}   sim BER = {ber:.4e}")
    print(f"  theo SER = {theoretical_ser(16, 14.0):.4e}")
    print(f"  BER ~= SER / log2(M) = {ser / 4:.4e}")
    print()

    print("=== Gray vs binary labeling @ 12 dB (QAM-16) ===")
    sg, bg = simulate(16, 12.0, trials=200_000, gray=True, seed=1)
    sb, bb = simulate(16, 12.0, trials=200_000, gray=False, seed=1)
    print(f"  Gray :  SER={sg:.4e}  BER={bg:.4e}")
    print(f"  Bin  :  SER={sb:.4e}  BER={bb:.4e}")
    print(f"  BER ratio (binary/gray) = {bb / bg:.2f}x")
    print()

    print("=== SER sweep: QAM-16 ===")
    sweep(16, [6, 8, 10, 12, 14, 16, 18, 20])

    print("=== SER sweep: QAM-64 ===")
    sweep(64, [10, 14, 18, 20, 22, 24])


if __name__ == "__main__":
    main()
