# Perceptual Audio Coding: MP3 and AAC

> MP3 (MPEG-1 Audio Layer III, ISO/IEC 11172-3, finalized 1993) and AAC (Advanced Audio Coding, ISO/IEC 13818-7, finalized 1997) are *perceptual* coders: they shrink 16-bit linear PCM at 44.1 kHz (1,411.2 kbps stereo) down to 96-320 kbps by Fourier-analyzing each 1024-sample (MP3) or 2048-sample (AAC) window, computing a frequency-domain masking threshold from the psychoacoustic model, and quantizing only the spectral components that rise above that threshold. The psychoacoustic model exploits two flaws in human hearing: **simultaneous masking** (a 1 kHz tone at 60 dB SPL masks a 1.1 kHz tone at 30 dB) and **temporal masking** (a loud sound suppresses perception of quiet sounds for 5-200 ms after it stops). MP3 uses a hybrid filter bank (32-band polyphase quadrature filter plus 6-point MDCT) at 1152 samples/frame, AAC uses a pure 2048-point MDCT with temporal noise shaping (TNS) and a more aggressive psychoacoustic model, and AAC is roughly 30% more efficient at the same perceptual quality. The standard quantization step is non-uniform, the bit reservoir lets frames borrow bits from neighbors, and the final step is Huffman coding of the quantized spectral coefficients. This lesson implements the threshold calculation, the bit-allocation loop, and a complete bitrate estimator that proves why a 3-minute song is 4 MB on a CD and 2.4 MB at 128 kbps.

**Type:** Learn
**Languages:** Python 3 (stdlib only), JSON output, ASCII plots
**Prerequisites:** Phase 13 lessons 01-08 (digital audio fundamentals, PCM), Chapter 2 Fourier transform, simple dB arithmetic
**Time:** ~75 minutes

## Learning Objectives

- Sketch the MP3/AAC encoder pipeline: filter bank or MDCT, psychoacoustic model, quantization loop, bit reservoir, Huffman.
- Compute the threshold of audibility curve and the simultaneous-masking threshold given a tonal input, and explain why the ear has a roughly 4-Bark-wide critical band.
- Implement bit allocation by signal-to-mask ratio (SMR) and verify that the chosen quantizer step size keeps quantization noise below the masked threshold.
- Compare MP3 (Layer III of MPEG-1, 1993) with AAC (MPEG-2 Part 7, 1997) on window size, filter bank, and target bitrate for a given quality.
- Estimate compression ratio and file size for a stereo 44.1 kHz signal at 96, 128, 192, and 256 kbps.
- Apply temporal masking by adding a post-mask window after each loud event and showing that the encoder can stop quantizing for ~50 ms.

## The Problem

A CD-quality stereo signal is 44,100 samples/second x 16 bits x 2 channels = 1,411,200 bits per second, or about 10 MB per minute. Over a 1 Mbps link, a CD stream cannot even keep up with the audio; over a 128 kbps 3G link it is hopeless. Lossless coders (FLAC, ALAC) reach 50-60% reduction. To stream music over the Internet, you need 10:1 to 20:1 compression, and the only way to reach that is lossy coding that throws away bits the human ear cannot perceive.

The trick is knowing which bits to throw away. That knowledge comes from **psychoacoustics**, the science of how humans perceive sound. Two effects in the inner ear let the encoder delete information with no audible penalty: a loud tone raises the audibility threshold of nearby frequencies (frequency masking), and a loud sound leaves the auditory nerve in a state of reduced sensitivity for tens of milliseconds after it stops (temporal masking). The encoder turns both effects into a *masking threshold* curve, and any spectral component below the curve is quantized coarsely or dropped entirely.

## The Concept

### The threshold of audibility

The ear is not a flat detector. Measured against a quiet background, a tone at 4 kHz is audible at about 0 dB SPL, but a tone at 100 Hz requires roughly 25 dB SPL before it is heard. The curve is roughly U-shaped, dropping from 60 dB at 20 Hz to 0 dB near 4 kHz, then climbing back to 80 dB at 16 kHz. Below this curve, no tone is audible, so the encoder can quantize those frequencies with extreme coarseness (or set them to zero) without anyone noticing.

### Frequency (simultaneous) masking

A loud sound also raises the threshold in nearby frequency bands. Imagine a 1 kHz masker at 70 dB SPL. It hides a 1.1 kHz tone at 40 dB that would otherwise be audible. The effect extends about one critical band on either side of the masker; at 1 kHz the critical band is about 160 Hz wide. The **Bark scale** captures this band structure: 1 Bark = one critical band, with 24 Bark covering the audible range up to 15.5 kHz. A masking threshold function m(b) defined in Bark is shifted upward by the masker's level, then mapped back into Hz to give the encoder a frequency-domain curve.

### Temporal masking

A loud sound also masks sounds that arrive *after* it ends, for about 5 to 200 ms, depending on the masker's duration and level. The recovery is roughly exponential: a 60 dB tone masks a 30 dB tone for ~150 ms after it stops, but only ~5 ms for a 40 dB tone. The encoder exploits this by quantizing aggressively in the period right after a loud note, knowing the listener cannot detect the noise.

### The MP3 filter bank and MDCT

MP3 splits the audio into 32 subbands with a polyphase quadrature filter (PQF) of length 512, then applies a 6-point (MP3) or 18-point (AAC) Modified Discrete Cosine Transform to each subband. The MDCT is the heart of modern audio coding: it is critically sampled (no overhead), produces real-valued coefficients, and uses window overlap to avoid blocking artifacts. With a 50% overlap, the effective block size is 1,152 samples in MP3 long blocks and 384 in MP3 short blocks. AAC doubles the long block to 2,048 samples, giving finer frequency resolution and better low-bitrate behavior.

### The psychoacoustic model

ISO/IEC 11172-3 Annex B defines two psychoacoustic models. Model 1 is faster and uses 12-tone grouping; Model 2 (used in most encoders) operates on 1,024-sample FFTs of the input, identifies tonal and noise maskers in each critical band, applies the spreading function m(b), and outputs a masking threshold curve in dB SPL. The encoder compares each MDCT coefficient to the threshold; if the coefficient falls below, it is discarded, and any quantization noise is allowed to rise up to the threshold itself without becoming audible.

### Quantization, the inner loop, and bit reservoir

Quantization is a non-uniform power-law: xq = sign(x) * |x|^(3/4) rounded to integer. The 3/4 power matches the ear's loudness-growth function and gives finer steps at low amplitudes. The encoder runs an *inner loop*: it raises the quantizer step size until the number of bits needed to Huffman-code the quantized coefficients fits the bit budget for the frame. If the frame is "easy" (mostly silence) and uses few bits, the leftover goes into the bit reservoir; if the next frame is "hard" (a drum hit, a sibilant) the encoder can borrow from the reservoir. The reservoir is the reason that brief transients do not force a global bitrate increase.

### MP3 vs AAC: what changed and why

| Property | MP3 (MPEG-1 Layer III) | AAC (MPEG-2/4 Part 7) |
|---|---|---|
| Year | 1993 | 1997 (MPEG-2), 1999/2003 (MPEG-4) |
| Filter bank | 32-band PQF + 6-point MDCT | Pure 1024/2048-point MDCT |
| Window sizes | 1,152 (long), 384 x 3 (short) | 2,048 (long), 256 x 8 (short) |
| Psychoacoustic model | 36 subbands | 49 Bark-scale bands, gain control |
| Bit reservoir | Per-frame, fixed | Per-channel, larger (TNS-enabled) |
| Stereo coding | Mid/side, intensity | Parametric, MPS 2.0, LTP, TNS |
| Typical transparent bitrate (stereo) | 192-256 kbps | 128-160 kbps |
| Patents | Expired (2017) | Some expired, licensing still active |

AAC gains its edge from a longer MDCT (sharper frequency resolution, less pre-echo on transients), temporal noise shaping (TNS, which lets the encoder place quantization noise *before* a transient instead of after), and a perceptually tuned Huffman codebook set. HE-AAC (a.k.a. AAC+) adds Spectral Band Replication (SBR) which keeps only the lower frequencies and reconstructs the highs at the decoder, reaching AAC quality at 48-64 kbps.

## Build It

`code/main.py` implements the core of the encoder as a teaching model. It does not produce a real MP3/AAC file; instead it shows, in the same order, how a real encoder decides what to throw away.

The script is structured in five stages:

1. **Signal generator.** Builds a 2-second 44.1 kHz stereo signal that contains (a) a 1 kHz sine wave at 60 dB SPL, (b) a 4 kHz tone that appears at t = 1.0 s, and (c) a low-level 100 Hz drone. The tones are easy to inspect and cover low, mid, and high frequencies.

2. **MDCT stage.** Applies a 2,048-point MDCT with a sine window to a stereo frame. The output is a 1,024 x 2 matrix of real spectral coefficients per frame. The script verifies perfect reconstruction by running the inverse MDCT and checking that the round-trip error is below 1e-9.

3. **Psychoacoustic threshold.** Computes the threshold of audibility at each MDCT bin using a tabulated threshold curve (the same shape that appears in ISO/IEC 11172-3 Annex B), then computes the simultaneous-masking threshold from the 1 kHz tone via a triangular spreading function in the Bark domain. The combined threshold in dB SPL is the per-bin floor below which quantization noise is inaudible.

4. **Bit allocation loop.** For each frame, sorts the spectral coefficients by their Signal-to-Mask Ratio (SMR = signal level minus masking threshold), and greedily allocates quantization steps so the quantization noise stays below the threshold. The number of allocated bits is the "size" of the frame in the bitstream. The script reports the average bits per frame and the per-frame fill of the bit reservoir.

5. **Bitrate estimator.** Computes the per-second output bitrate, the file size for a 3-minute song, and the compression ratio relative to 16-bit linear PCM. The script writes a JSON report to `outputs/perceptual_coding_report.json` and prints a comparison table for target bitrates 96, 128, 192, 256 kbps.

Run:

```bash
python3 phases/13-streaming-real-time-media-and-content-delivery/09-perceptual-audio-coding-mp3-aac/code/main.py
```

Expected output (truncated):

```text
frame 0 : 1024 coeffs, SMR budget = 1830 bits
frame 1 : 1024 coeffs, SMR budget = 1980 bits
...
bitrate report:
  96 kbps  : 3-min file = 2.16 MB, ratio 11.1:1
  128 kbps : 3-min file = 2.88 MB, ratio  8.3:1
  192 kbps : 3-min file = 4.32 MB, ratio  5.6:1
  256 kbps : 3-min file = 5.76 MB, ratio  4.2:1
```

## Use It

| Encoder | Container | Use case | Typical bitrate (stereo) | Latency |
|---|---|---|---|---|
| LAME MP3 | `.mp3` | legacy music downloads | 128-192 kbps | ~50 ms |
| Fraunhofer AAC-LC | `.m4a` (MP4) | iTunes, Apple Music, YouTube | 96-160 kbps | ~20-40 ms |
| HE-AAC v1 (AAC+SBR) | `.m4a` | low-bitrate streaming | 48-64 kbps | ~80 ms |
| HE-AAC v2 (AAC+SBR+PS) | `.m4a` | very low bitrate, mono-coded stereo | 32-48 kbps | ~120 ms |
| Opus | `.opus`, `.webm` | WebRTC, modern streaming | 64-128 kbps | 5-60 ms (configurable) |
| FLAC | `.flac` | archival, lossless | ~700-1100 kbps | 0 (block-based) |

For a target quality of "transparent to the CD" on rock/pop music, AAC at 128 kbps and MP3 at 192 kbps are roughly equivalent. For a piano concert, AAC needs at least 160 kbps and MP3 needs at least 256 kbps. For speech, Opus at 32 kbps and HE-AAC v2 at 24 kbps are both transparent.

## Ship It

`outputs/perceptual_coding_report.json` records the per-frame bit allocation, the average and peak bits per frame, the effective output bitrate, and the file size for a 3-minute song at four common targets. The SVG diagram in `assets/perceptual-audio-coding-mp3-aac.svg` plots (a) the input spectrum, (b) the masking threshold, and (c) the quantization noise that the encoder is willing to leave in the output.

## Exercises

1. **Threshold of audibility.** Implement the absolute threshold in dB SPL across 0-16 kHz using a piecewise function. Verify that your curve matches the textbook plot to within 3 dB at 100 Hz, 1 kHz, and 8 kHz.
2. **Critical band spread.** Replace the triangular Bark-domain spreading function with a real cochlear filter shape (e.g., a Gaussian centered on the masker in Bark). Plot the resulting masking threshold.
3. **Temporal masking.** Add a post-mask window of 150 ms after a 60 dB tone. Show that quantization noise inside that window is inaudible, and reduce the bit allocation accordingly.
4. **Bitrate sweep.** Run the encoder with target bitrates 64, 96, 128, 192, 256, 320 kbps and plot the per-frame bit usage as a function of frame index. At which bitrate does the bit reservoir overflow?
5. **AAC vs MP3.** Implement the same encoder with MP3's 576-point MDCT and a 32-band PQF. Compare the average bits per frame to the pure-MDCT version for the same input.
6. **Window switching.** Detect a transient (e.g., the first 5 ms after a 4 kHz onset) and switch from long to short windows in the MDCT. Verify that the pre-echo artifact is reduced.

## Key Terms

| Term | Definition |
|---|---|
| PCM | Pulse-Code Modulation; raw digital audio samples |
| MDCT | Modified Discrete Cosine Transform; critically-sampled lapped transform |
| PQF | Polyphase Quadrature Filter; 32-band subband filter used in MP3 |
| Bark | Psychoacoustic frequency scale; 1 Bark = one critical band, 24 Bark = 0-15.5 kHz |
| SMR | Signal-to-Mask Ratio; the dB gap between a spectral line and the masking threshold |
| Spreading function | Model of how masker energy leaks into adjacent critical bands |
| Temporal masking | Forward/backward masking of quiet sounds by loud ones for 5-200 ms |
| Bit reservoir | Bank of bits a frame can borrow from or lend to its neighbors |
| TNS | Temporal Noise Shaping; AAC tool that controls pre-echo |
| SBR | Spectral Band Replication; reconstructs high frequencies from low ones |
| LC-AAC | Low-Complexity AAC; the MPEG-2 AAC profile used by iTunes and YouTube |
| HE-AAC | High-Efficiency AAC; LC-AAC plus SBR; half the bitrate at the same quality |

## Further Reading

- K. Brandenburg, "MP3 and AAC Explained," Proc. AES 17th Intl. Conf. on High Quality Audio Coding, 1999.
- ISO/IEC 11172-3:1993, "Information technology - Coding of moving pictures and associated audio for digital storage media at up to about 1.5 Mbit/s - Part 3: Audio."
- ISO/IEC 13818-7:1997, "Generic coding of moving pictures and associated audio information - Part 7: Advanced Audio Coding (AAC)."
- ISO/IEC 14496-3:2009, "Coding of audio-visual objects - Part 3: Audio" (HE-AAC, AAC-LC, SBR).
- J. D. Johnston and A. J. Ferreira, "Sum-difference stereo transform coding," ICASSP 1992, pp. 569-572.
- M. Bosi and R. E. Goldberg, *Introduction to Digital Audio Coding and Standards*, Springer, 2003.
- Recommendation ITU-R BS.1387, "Method for objective measurements of perceived audio quality (PEAQ)."
- E. Zwicker and H. Fastl, *Psychoacoustics: Facts and Models*, Springer, 2nd ed., 1999.
