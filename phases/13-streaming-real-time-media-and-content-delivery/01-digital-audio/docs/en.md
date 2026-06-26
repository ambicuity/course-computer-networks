# Digital Audio

> Sound is a one-dimensional acoustic pressure wave; the human ear hears roughly 20 Hz–20 kHz and perceives loudness logarithmically in decibels (10 log(A/B)), giving a dynamic range exceeding 1,000,000:1. An ADC samples the wave at discrete intervals and the Nyquist theorem proves that sampling at 2f suffices to reconstruct a signal whose highest component is f. Telephone PCM uses 8-bit samples at 8,000 Hz (64,000 bps) with nonlinear µ-law (North America/Japan) or A-law (Europe/international) companding; audio CDs use 16-bit linear samples at 44,100 Hz, yielding 705.6 kbps mono and 1.411 Mbps stereo — above the Nyquist cutoff of 22,050 Hz but below the ear's full range. Quantization noise is the error introduced by finite bits per sample (16 bits = 65,536 levels). MP3 (MPEG-1 audio layer 3) and AAC (MPEG-4 default) are perceptual coders: a Fourier transform extracts spectral power, a psychoacoustic model drops frequencies below the threshold of audibility and those masked by louder nearby bands (frequency masking), plus a short recovery window after a loud sound stops (temporal masking), and Huffman coding packs the survivors. MP3 can take a stereo CD to 96 kbps with little perceived loss; AAC needs ≥128 kbps for piano concerts. The ear is sensitive to jitter of only a few milliseconds, far more than the eye — this drives the entire design of real-time media transport.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python (stdlib)
**Prerequisites:** Phase 2 sampling/Nyquist; Phase 11 RTP basics
**Time:** ~70 minutes

## Learning Objectives

- Compute PCM bit rates from sample rate, bits per sample, and channel count, and explain why telephone PCM is 64 kbps and CD audio is 1.411 Mbps stereo.
- State the Nyquist sampling criterion (sample at 2f) and explain why CDs sample at 44.1 kHz to cover a 20 kHz hearing range.
- Distinguish waveform coding from perceptual coding, and name the two masking effects (frequency, temporal) that MP3/AAC exploit.
- Quantify quantization noise as a function of bits per sample (2^n levels) and explain why 16-bit CD audio does not cover the ear's full dynamic range.
- Explain why millisecond-scale jitter degrades perceived audio more than video, and connect this to later streaming/conferencing lessons.

## The Problem

A network engineer is sizing a voice trunk and a music streaming service. The voice call must fit the G.711 telephony model; the music service must deliver "CD quality" without saturating a 1 Mbps broadband link. The engineer cannot pick bit rates, codecs, or buffer depths without understanding what "digital audio" actually is: how a continuous pressure wave becomes bits, how many bits, and which bits can be thrown away without a human noticing. Get any of this wrong and the call sounds robotic, the stream stalls, or the bandwidth bill doubles.

## The Concept

### The acoustic-to-digital chain

Sound strikes a microphone and becomes an analog electrical signal — amplitude as a function of time. An Analog-to-Digital Converter (ADC) samples this signal every ΔT seconds and emits a binary number. The reverse path runs a Digital-to-Analog Converter (DAC) into a loudspeaker. The chain is: acoustic wave → microphone → ADC → bits → network/storage → DAC → speaker → ear. Every later protocol (RTP, RTSP, FEC, interleaving) exists to move those bits with the right timing and loss budget.

### Sampling and the Nyquist theorem

If a sound is a linear superposition of sine waves with the highest component at frequency f, the Nyquist theorem (Chapter 2) says sampling at 2f is sufficient; sampling faster detects no new information. Telephone PCM samples 8,000 times/sec, so frequencies above 4 kHz are lost — acceptable for speech. CDs sample 44,100 times/sec, capturing up to 22,050 Hz, which covers human hearing well but not dogs. The choice of 44.1 kHz is historical (adapted from PCM video recorders used for master tapes).

| Source | Sample rate | Bits/sample | Channels | Raw bit rate |
|--------|-------------|-------------|----------|--------------|
| Telephone PCM (G.711) | 8,000 Hz | 8 (nonlinear) | 1 | 64 kbps |
| CD audio | 44,100 Hz | 16 (linear) | 2 (stereo) | 1.411 Mbps |
| CD mono | 44,100 Hz | 16 | 1 | 705.6 kbps |
| AAC typical | 44,100 Hz | compressed | 2 | 128 kbps |
| MP3 rock | 44,100 Hz | compressed | 2 | 96 kbps |

### Quantization noise

An n-bit sample allows 2^n distinct values. A 4-bit sample gives 9 levels from −1.00 to +1.00 in steps of 0.25; an 8-bit sample gives 256; a 16-bit sample gives 65,536. The error between the true amplitude and the nearest representable level is quantization noise. The ear's dynamic range exceeds 1,000,000:1 (120 dB), but 16 bits give only 65,536:1 (~96 dB), so even CD audio has measurable quantization noise — which is why audiophiles preferred 33-RPM LPs (no Nyquist cutoff, no quantization noise, but scratches). The `code/main.py` quantizer demonstrates this directly by reducing a sine wave to n bits and printing the error.

### Decibels and loudness

The ear perceives loudness logarithmically. The ratio of two sounds with power A and B is expressed in dB as 10 log10(A/B). With the lower limit of audibility (≈20 µPa at 1 kHz) defined as 0 dB, ordinary conversation is ~50 dB and the pain threshold is ~120 dB. The full dynamic range is a factor of more than 1,000,000. This logarithmic perception is why companding (µ-law, A-law) works: it allocates more levels to quiet sounds where the ear discriminates finely, and fewer to loud sounds where it does not.

### PCM telephony: G.711, µ-law, A-law

Pulse code modulation in the telephone system uses 8-bit samples 8,000 times/sec. The scale is nonlinear to minimize perceived distortion: North America and Japan use µ-law; Europe and the international standard use A-law. Both yield 64,000 bps — the canonical DS0 channel rate that Echo Cancellation, ATM, and ISDN all assume. Nonlinear quantization roughly doubles the effective dynamic range compared with linear 8-bit sampling.

### Compression: encode-once vs encode-live

Compression has two asymmetries. First, stored media is encoded once and decoded thousands of times, so slow/expensive encoding is fine if decoding is fast and cheap. Live audio (VoIP) must encode in real time, so it uses lighter compression. Second, audio compression is lossy: the decoded output need not be bit-identical, only perceptually identical. Accepting small losses unlocks large compression ratios.

### Perceptual coding: MP3 and AAC

MP3 (MPEG-1 audio layer 3 — *not* "MPEG version 3") and AAC (Advanced Audio Coding, MPEG-4 default) use perceptual coding based on psychoacoustics. The pipeline:

1. Sample the waveform (8–96 kHz for AAC, often 44.1 kHz).
2. Process samples in small batches through a bank of digital filters to get frequency bands.
3. Feed frequency information into a psychoacoustic model to find masked frequencies.
4. Divide the bit budget across bands — more bits to unmasked bands with high spectral power, zero bits to masked bands.
5. Huffman-encode the survivors.

Two masking effects are exploited. **Frequency masking**: a loud sound in one band raises the audibility threshold of nearby bands, so softer sounds there can be dropped entirely (the jackhammer-and-flute example). **Temporal masking**: after a loud sound stops, the ear's gain takes a finite time to recover, so masked frequencies can be omitted for a short window after the loud signal ends. The `code/main.py` masking demo prints which frequency bands survive a simple masking threshold.

MP3 compresses stereo rock to 96 kbps with little perceived loss; AAC at ≥128 kbps is needed for a piano concert because the signal-to-noise ratio of classical material is much higher. `assets/digital-audio.svg` diagrams the perceptual-coding pipeline from waveform to Huffman-coded output.

### Jitter sensitivity and why this lesson matters for streaming

The ear is sensitive to sound variations lasting only a few milliseconds; the eye does not notice light-level changes of a few milliseconds. This single physiological fact is why millisecond jitter during playout degrades audio quality far more than video quality, and it drives the entire design of playout buffers (Lesson 03), short RTP packets (Lesson 04), and DS/Expedited Forwarding markings for VoIP. Quantization noise and compression artifacts are in-band; jitter is a transport-layer artifact that the codec cannot hide.

## Build It

1. Run `python3 code/main.py` and inspect the quantization error table for 4-bit, 8-bit, and 16-bit sampling.
2. Read the PCM bit-rate table the program prints and verify 64 kbps (telephone) and 1.411 Mbps (CD stereo) by hand.
3. Read the masking demo output: which frequency bands are dropped when a 150 Hz masker is present?
4. Open `assets/digital-audio.svg` and trace the perceptual-coding pipeline: waveform → filter bank → psychoacoustic model → bit allocation → Huffman.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Size a voice trunk | PCM bit rate = 64 kbps × channels | Matches G.711 DS0 math |
| Size a music stream | CD stereo = 1.411 Mbps raw; AAC ≈ 128 kbps compressed | Compression ratio ~11:1, fits broadband |
| Choose a codec for speech vs music | G.711 for telephony; AAC for music; MP3 for legacy | Codec matches latency and quality constraints |
| Diagnose "thin" audio | Check sample rate, bits/sample, and whether perceptual coder dropped too many bands | Quantization or over-aggressive masking identified |
| Explain jitter sensitivity | Ear resolves ms-scale variations; eye does not | Connects to playout buffer and VoIP packet size |

## Ship It

Produce `outputs/audio-bitrate-worksheet.md`: for a given source (telephone, CD, AAC stream), record sample rate, bits/sample, channels, raw rate, compressed rate, compression ratio, and the masking/quantization trade-off that was accepted. This worksheet is reusable whenever you size a media path.

## Exercises

1. A system samples at 22,050 Hz with 16-bit linear samples, mono. What is the raw bit rate, and what is the highest frequency it can represent? Why is this below CD quality?
2. Compute the dynamic range in dB of 8-bit µ-law, 16-bit linear, and 24-bit linear PCM. Which comes closest to the ear's 120 dB range?
3. A loud 200 Hz tone is present. Using the frequency-masking principle, which nearby bands can be dropped, and what does the encoder do with the freed bit budget?
4. Why must a live VoIP call use a different encoder (or parameters) than a stored music file, even if both target the same bit rate? Name both asymmetries.
5. An MP3 stream at 96 kbps sounds fine for rock but artifact-laden for a piano recital. Explain in terms of signal-to-noise ratio and the psychoacoustic model.
6. A listener reports "robotic" voice on a VoIP call. Distinguish quantization noise, codec over-compression, and jitter as candidate causes, and state the evidence you would collect first.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| PCM | "digital phone audio" | Pulse Code Modulation; 8-bit 8 kHz samples = 64 kbps DS0 |
| Nyquist theorem | "sample twice as fast" | Sampling at 2f suffices to reconstruct a signal band-l to f |
| Quantization noise | "grainy sound" | Error from finite bits/sample; 16 bits = 65,536 levels |
| µ-law / A-law | "phone companding" | Nonlinear 8-bit quantization; µ-law in NA/Japan, A-law in Europe |
| Perceptual coding | "MP3 trick" | Drop frequencies the ear cannot hear due to masking |
| Frequency masking | "loud hides soft" | A loud band raises the audibility threshold of nearby bands |
| Temporal masking | "ear recovery lag" | Masked frequencies stay inaudible briefly after the masker stops |
| AAC | "better MP3" | Advanced Audio Coding; MPEG-4 default audio encoder |
| Decibel (dB) | "loudness unit" | 10 log10(A/B); logarithmic power ratio the ear matches |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Section 7.4.1 (Digital Audio).
- ITU-T G.711 — Pulse code modulation of voice frequencies.
- ISO/IEC 11172-3 — MPEG-1 audio (includes MP3, layer 3).
- ISO/IEC 14496-3 — MPEG-4 audio (AAC).
- Brandenburg, K. (1999), "MP3 and AAC Explained," *AES 17th Int. Conf. on High-Quality Audio Coding*.
- RFC 3119 — A more efficient loss-tolerant RTP packing for compressed audio.