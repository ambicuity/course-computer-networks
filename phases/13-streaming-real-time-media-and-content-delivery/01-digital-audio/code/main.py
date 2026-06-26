"""Digital Audio: sampling, quantization, PCM bit rates, and perceptual masking.

A stdlib-only demonstration that walks through the core numbers behind
digital audio as carried over networks: Nyquist sampling, quantization
noise, telephone PCM (G.711) and CD-audio bit rates, and a simple
perceptual-masking decision showing which frequency bands an MP3/AAC
style encoder would drop.

Run:  python3 main.py
Exit: 0
"""

from __future__ import annotations

import math
import struct
from typing import List, Tuple


def nyquist_limit(sample_rate: float) -> float:
    """Highest frequency (Hz) a given sample rate can represent."""
    return sample_rate / 2.0


def pcm_bit_rate(sample_rate: float, bits_per_sample: int, channels: int) -> float:
    """Raw PCM bit rate in bits per second."""
    return sample_rate * bits_per_sample * channels


def quantization_levels(bits_per_sample: int) -> int:
    """Number of distinct amplitude levels representable by n bits."""
    return 2 ** bits_per_sample


def dynamic_range_db(bits_per_sample: int) -> float:
    """Approximate dynamic range in dB for linear PCM (≈ 6.02 * bits)."""
    return 6.02 * bits_per_sample


def quantize_sine(amplitude: float, bits_per_sample: int, n: int = 8) -> List[Tuple[float, float, float]]:
    """Quantize a unit-amplitude sine over one period to n bits.

    Returns (t, true, quantized) tuples for n sample points.
    """
    half = quantization_levels(bits_per_sample) // 2
    step = 1.0 / half
    out: List[Tuple[float, float, float]] = []
    for i in range(n):
        t = i / n
        true = amplitude * math.sin(2.0 * math.pi * t)
        q_level = max(-half, min(half - 1, round(true / step)))
        out.append((t, true, q_level * step))
    return out


def quantization_error_table() -> None:
    """Print quantization error for a few bit depths."""
    print("=== Quantization of a unit-amplitude sine (8 samples/period) ===")
    print(f"{'bits':>4} {'levels':>8} {'max |err|':>12} {'rms err':>12}")
    for bits in (4, 8, 16):
        rows = quantize_sine(1.0, bits, n=8)
        errs = [abs(t - q) for _, t, q in rows]
        max_err = max(errs)
        rms_err = math.sqrt(sum(e * e for e in errs) / len(errs))
        print(f"{bits:>4} {quantization_levels(bits):>8} {max_err:>12.6f} {rms_err:>12.6f}")
    print()


def pcm_rate_table() -> None:
    """Print canonical PCM bit rates."""
    print("=== Canonical PCM bit rates ===")
    rows = [
        ("Telephone G.711", 8000, 8, 1),
        ("CD mono", 44100, 16, 1),
        ("CD stereo", 44100, 16, 2),
        ("DAT stereo", 48000, 16, 2),
        ("Studio 24-bit stereo", 96000, 24, 2),
    ]
    print(f"{'source':>22} {'Hz':>8} {'bits':>4} {'ch':>3} {'kbps':>10}")
    for name, sr, bits, ch in rows:
        rate = pcm_bit_rate(sr, bits, ch)
        print(f"{name:>22} {sr:>8} {bits:>4} {ch:>3} {rate/1000:>10.1f}")
    print()


def decibel_ratio(power_a: float, power_b: float) -> float:
    """dB = 10 log10(A/B)."""
    if power_b <= 0:
        raise ValueError("reference power must be positive")
    return 10.0 * math.log10(power_a / power_b)


def loudness_table() -> None:
    """Print reference loudness levels."""
    print("=== Loudness references (0 dB = threshold of audibility) ===")
    refs = [
        ("Threshold of audibility", 1.0),
        ("Whisper", 100.0),
        ("Ordinary conversation", 100_000.0),
        ("Traffic", 1_000_000.0),
        ("Pain threshold", 1_000_000_000_000.0),
    ]
    print(f"{'source':>28} {'rel.power':>14} {'dB':>8}")
    for name, p in refs:
        print(f"{name:>28} {p:>14.0f} {decibel_ratio(p, 1.0):>8.1f}")
    print()


# ---- Perceptual masking demo ---------------------------------------------

def threshold_of_audibility(freq_hz: float) -> float:
    """A crude approximation of the ear's quiet-curve (dB SPL).

    The real curve dips around 2-4 kHz (ear most sensitive) and rises at
    the extremes; we use a simple piecewise model for the demo.
    """
    f = max(freq_hz, 20.0)
    if f < 500:
        return 60 - 10 * math.log10(f / 20.0)
    if f < 4000:
        return 20 - 5 * math.log10(f / 1000.0)
    return 20 + 8 * math.log10(f / 4000.0)


def masking_threshold_lift(masker_freq: float, masker_db: float, freq_hz: float) -> float:
    """How much the audibility threshold at freq_hz is raised by a tone
    at masker_freq of level masker_db. Simplified triangular spread."""
    # spread: ±1 octave, linear falloff in dB
    if masker_freq <= 0:
        return 0.0
    octaves = abs(math.log2(freq_hz / masker_freq)) if freq_hz > 0 else 99
    if octaves > 1.5:
        return 0.0
    spread = masker_db * (1.0 - octaves / 1.5)
    return max(0.0, spread)


def perceptual_masking_demo() -> None:
    """Show which bands an MP3/AAC-style encoder would keep/drop."""
    print("=== Perceptual masking demo (masker = 150 Hz tone at 80 dB) ===")
    bands = [60, 100, 125, 150, 200, 300, 500, 1000, 2000, 4000, 8000, 16000]
    masker_freq, masker_db = 150.0, 80.0
    print(f"{'band Hz':>9} {'quiet thr':>10} {'masked thr':>11} {'signal dB':>10} {'keep?':>7}")
    for f in bands:
        quiet = threshold_of_audibility(f)
        lift = masking_threshold_lift(masker_freq, masker_db, f)
        masked = quiet + lift
        # suppose the signal in this band is 30 dB (moderate)
        signal_db = 30.0
        keep = signal_db > masked
        print(f"{f:>9} {quiet:>10.1f} {masked:>11.1f} {signal_db:>10.1f} {'yes' if keep else 'drop':>7}")
    print("\nNote: bands near 150 Hz have their threshold raised above the signal,")
    print("so a perceptual coder would allocate them zero bits (frequency masking).")
    print()


# ---- Simple WAV-style byte packing (no file I/O) -------------------------

def pack_pcm_samples(samples: List[float], bits_per_sample: int) -> bytes:
    """Pack float samples in [-1,1] into little-endian PCM bytes (8 or 16 bit)."""
    if bits_per_sample == 16:
        out = bytearray()
        for s in samples:
            v = int(max(-1.0, min(1.0, s)) * 32767)
            out += struct.pack('<h', v)
        return bytes(out)
    if bits_per_sample == 8:
        out = bytearray()
        for s in samples:
            v = int((max(-1.0, min(1.0, s)) + 1.0) * 127.5)
            out.append(v & 0xFF)
        return bytes(out)
    raise ValueError("only 8 or 16 bit supported in demo")


def wav_byte_rate_demo() -> None:
    """Show how many bytes/sec of raw PCM a few sources produce."""
    print("=== Raw PCM byte rate (for network sizing) ===")
    cases = [
        ("G.711 voice", 8000, 8, 1),
        ("CD stereo", 44100, 16, 2),
        ("AAC target", 44100, 0, 2),  # 0 bits = compressed, special
    ]
    for name, sr, bits, ch in cases:
        if bits == 0:
            # compressed target
            print(f"{name:>14}: ~128 kbps (AAC), ~11:1 vs CD stereo")
            continue
        rate_bps = pcm_bit_rate(sr, bits, ch)
        rate_Bps = rate_bps / 8.0
        print(f"{name:>14}: {rate_bps/1000:.1f} kbps  ({rate_Bps:.0f} bytes/sec)")
    print()


def main() -> None:
    print("Digital Audio — sampling, quantization, bit rates, masking\n")
    # 1. Nyquist
    print("=== Nyquist limits ===")
    for sr in (8000, 22050, 44100, 48000, 96000):
        print(f"  sample rate {sr:>6} Hz -> max frequency {nyquist_limit(sr):.0f} Hz")
    print()

    quantization_error_table()
    pcm_rate_table()
    loudness_table()
    wav_byte_rate_demo()
    perceptual_masking_demo()

    # Demonstrate packing a few samples
    sine_8 = [math.sin(2 * math.pi * i / 8) for i in range(8)]
    packed = pack_pcm_samples(sine_8, 16)
    print(f"=== Packed 8 sine samples as 16-bit PCM: {len(packed)} bytes ===")
    print("  " + " ".join(f"{b:02x}" for b in packed))
    print()

    print("Done. All demonstrations completed.")


if __name__ == "__main__":
    main()