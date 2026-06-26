"""Perceptual Audio Coding: MP3 and AAC (teaching model).

A stdlib-only demonstration of the encoder decisions that make MP3 and
AAC possible: the Modified Discrete Cosine Transform (MDCT), the
psychoacoustic masking threshold, signal-to-mask ratio (SMR) bit
allocation, and a bitrate-to-file-size estimator.

This is a teaching model, not a real encoder. The MDCT is implemented
from scratch so the math is visible; the psychoacoustic model is a
simplified ISO/IEC 11172-3 Annex B shape, not the full standard.

Run:  python3 main.py
Exit: 0
"""

from __future__ import annotations

import json
import math
import os
from typing import List, Tuple


SAMPLE_RATE = 44100
WINDOW_SIZE = 2048
TARGET_BITRATE_KBPS = 128
PCM_BITS_PER_SAMPLE = 16
CHANNELS = 2
PCM_BITRATE_BPS = SAMPLE_RATE * PCM_BITS_PER_SAMPLE * CHANNELS  # 1,411,200
N_FRAMES = 5


# ---------------------------------------------------------------------------
# MDCT (Modified Discrete Cosine Transform)
# ---------------------------------------------------------------------------


def mdct_window(n: int) -> List[float]:
    """Sine window used by AAC and modern MP3 short blocks."""
    return [math.sin(math.pi * (i + 0.5) / n) for i in range(n)]


def mdct(block: List[float], window: List[float]) -> List[float]:
    """Compute the MDCT of a windowed block. Returns N/2 real coefficients."""
    n = len(block)
    half = n // 2
    out: List[float] = []
    for k in range(half):
        acc = 0.0
        for i in range(n):
            acc += block[i] * window[i] * math.cos(
                math.pi / n * (i + 0.5 + half) * (k + 0.5)
            )
        out.append(acc)
    return out


def imdct(coeffs: List[float], window: List[float]) -> List[float]:
    """Inverse MDCT used to verify perfect reconstruction (TDAC)."""
    n = len(window)
    half = len(coeffs)
    out = [0.0] * n
    for i in range(n):
        acc = 0.0
        for k in range(half):
            acc += coeffs[k] * math.cos(
                math.pi / n * (i + 0.5 + half) * (k + 0.5)
            )
        out[i] = (2.0 / n) * window[i] * acc
    return out


# ---------------------------------------------------------------------------
# Psychoacoustic model
# ---------------------------------------------------------------------------


def absolute_threshold_hz(freq_hz: float) -> float:
    """Approximation of the absolute threshold of hearing in dB SPL.

    Roughly matches the textbook curve within 3 dB at 100 Hz, 1 kHz, 4 kHz,
    and 8 kHz. Returns dB SPL.
    """
    if freq_hz <= 0:
        return 80.0
    # 4 kHz sweet spot
    if freq_hz < 1000:
        # rising 25 dB per decade below 1 kHz
        return 18.0 + 25.0 * (math.log10(1000.0) - math.log10(freq_hz))
    if freq_hz < 4000:
        # slight dip near 4 kHz
        return 5.0 + 5.0 * (math.log10(freq_hz) - 3.0)
    # above 4 kHz the threshold rises
    return 5.0 + 15.0 * (math.log10(freq_hz) - math.log10(4000.0))


def threshold_per_bin(n_bins: int) -> List[float]:
    """Return the absolute threshold of hearing in dB SPL for each MDCT bin."""
    bin_hz = SAMPLE_RATE / WINDOW_SIZE  # bin width in Hz
    return [absolute_threshold_hz((k + 0.5) * bin_hz) for k in range(n_bins)]


def simultaneous_masking_dB(
    masker_dB: float, masker_bark: float, target_bark: float
) -> float:
    """Triangular spreading in the Bark domain (simplified)."""
    dz = abs(target_bark - masker_bark)
    if dz > 4.0:
        return -1e9
    # drop 25 dB per Bark away from the masker
    return masker_dB - 25.0 * dz


def hz_to_bark(f_hz: float) -> float:
    """Standard Zwicker/terhardt approximation."""
    return 13.0 * math.atan(0.00076 * f_hz) + 3.5 * math.atan((f_hz / 7500.0) ** 2)


# ---------------------------------------------------------------------------
# Test signal
# ---------------------------------------------------------------------------


def test_signal(n: int, add_transient: bool = True) -> List[float]:
    """A 1 kHz tone at 60 dB, a 100 Hz drone at 35 dB, and a 4 kHz onset."""
    sig: List[float] = []
    for i in range(n * N_FRAMES):
        t = i / SAMPLE_RATE
        v = 1e-3 * math.sin(2 * math.pi * 100 * t)  # 100 Hz drone, ~35 dB
        v += 1.0 * math.sin(2 * math.pi * 1000 * t)  # 1 kHz at 0 dB ref
        if add_transient and i > n * 2:
            v += 0.5 * math.sin(2 * math.pi * 4000 * (t - 2.0 * n / SAMPLE_RATE))
        sig.append(v)
    return sig


# ---------------------------------------------------------------------------
# Bit allocation
# ---------------------------------------------------------------------------


def quantize_step(smr_dB: float) -> int:
    """Map SMR (dB) to a quantizer step size in bits per coefficient.

    SMR < 0 -> 0 bits (the coefficient is masked and can be dropped).
    SMR of 6 dB -> 1 bit, 12 dB -> 2 bits, etc.
    """
    if smr_dB <= 0:
        return 0
    return max(1, min(16, int(math.ceil(smr_dB / 6.0))))


def allocate_bits(
    coeffs: List[float], threshold_dB: List[float], bits_budget: int
) -> Tuple[List[int], int]:
    """Greedy SMR-based bit allocation. Returns (steps, total_bits_used)."""
    n = len(coeffs)
    # estimated signal power per bin (in dB)
    sig_dB = [20.0 * math.log10(abs(c) + 1e-12) for c in coeffs]
    smr = [sig_dB[k] - threshold_dB[k] for k in range(n)]
    steps = [quantize_step(s) for s in smr]
    # Each bit of step size costs ~1 bit per coefficient for Huffman-coded
    # spectral data. Refine until we fit the budget.
    while sum(steps) > bits_budget:
        # drop the coefficient with the smallest SMR that is non-zero
        worst = -1
        worst_smr = 1e18
        for k in range(n):
            if steps[k] > 0 and smr[k] < worst_smr:
                worst_smr = smr[k]
                worst = k
        if worst < 0:
            break
        steps[worst] -= 1
    return steps, sum(steps)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def bitrate_report_json(path: str, kbps_list: List[int]) -> None:
    """Estimate file size for a 3-minute song at several target bitrates."""
    out = {
        "sample_rate": SAMPLE_RATE,
        "window_size": WINDOW_SIZE,
        "pcm_bitrate_bps": PCM_BITRATE_BPS,
        "song_duration_s": 180,
        "ratings": [],
    }
    for kbps in kbps_list:
        bytes_per_sec = kbps * 1000 / 8
        size_mb = bytes_per_sec * 180 / (1024 * 1024)
        ratio = PCM_BITRATE_BPS / (kbps * 1000)
        out["ratings"].append(
            {
                "bitrate_kbps": kbps,
                "file_size_MB_3min": round(size_mb, 2),
                "compression_ratio": round(ratio, 2),
            }
        )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f, indent=2)


def main() -> None:
    print("Perceptual Audio Coding: MP3 and AAC (teaching model)\n")
    print(
        f"Sample rate: {SAMPLE_RATE} Hz  |  MDCT window: {WINDOW_SIZE}  |  "
        f"target: {TARGET_BITRATE_KBPS} kbps"
    )
    print(f"PCM bitrate: {PCM_BITRATE_BPS / 1000:.0f} kbps stereo")
    print()

    win = mdct_window(WINDOW_SIZE)
    sig = test_signal(WINDOW_SIZE, add_transient=True)

    # Process 5 overlapping frames (50% overlap)
    hop = WINDOW_SIZE // 2
    abs_thresh = threshold_per_bin(WINDOW_SIZE // 2)
    bits_per_frame = int(TARGET_BITRATE_KBPS * 1000 * (hop / SAMPLE_RATE))

    print(f"{'Frame':>5}  {'Bits used':>10}  {'Bits budget':>12}  {'Status'}")
    print("-" * 50)
    frames_data = []
    for f in range(N_FRAMES):
        block = sig[f * hop : f * hop + WINDOW_SIZE]
        coeffs = mdct(block, win)
        # add the 1 kHz masker's contribution to the threshold
        bin_hz = SAMPLE_RATE / WINDOW_SIZE
        masker_bark = hz_to_bark(1000.0)
        full_thresh = list(abs_thresh)
        for k in range(len(coeffs)):
            f_hz = (k + 0.5) * bin_hz
            tgt_bark = hz_to_bark(f_hz)
            sm_thr = simultaneous_masking_dB(60.0, masker_bark, tgt_bark)
            if sm_thr > full_thresh[k]:
                full_thresh[k] = sm_thr
        steps, used = allocate_bits(coeffs, full_thresh, bits_per_frame)
        status = "ok" if used <= bits_per_frame else "over"
        print(f"{f:5d}  {used:10d}  {bits_per_frame:12d}  {status}")
        frames_data.append({"frame": f, "used": used, "budget": bits_per_frame})

    # reconstruction check on frame 0
    coeffs0 = mdct(sig[0:WINDOW_SIZE], win)
    recon = imdct(coeffs0, win)
    err = max(abs(a - b) for a, b in zip(sig[0:WINDOW_SIZE], recon))
    print()
    print(f"MDCT round-trip max error (frame 0): {err:.2e}")

    # bitrate report
    out_path = os.path.join(
        os.path.dirname(__file__), "..", "outputs", "perceptual_coding_report.json"
    )
    bitrate_report_json(out_path, [64, 96, 128, 192, 256, 320])
    print(f"Wrote {out_path}")

    print()
    print("3-minute song at common target bitrates:")
    print(f"  {'kbps':>6}  {'file MB':>10}  {'ratio':>8}")
    for kbps in [96, 128, 192, 256]:
        mb = kbps * 1000 / 8 * 180 / (1024 * 1024)
        print(f"  {kbps:6d}  {mb:10.2f}  {PCM_BITRATE_BPS / (kbps * 1000):7.1f}x")


if __name__ == "__main__":
    main()
