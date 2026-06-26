# Digital Video

> A video is a sequence of frames, each a rectangular grid of pixels. The eye retains an image for milliseconds; if frames are drawn at 24, 25, or 30 per second the brain perceives continuous motion. Standard frame rates are 24 fps (35 mm film), 30 fps (NTSC, really 29.97 after color needed extra bandwidth), and 25 fps (PAL). Color uses 8 bits each for R, G, B — 24 bits/pixel, about 16 million colors, more than the eye distinguishes. Common Internet frame sizes: 320×240 (low-res, 4:3), 640×480 (full-screen, NTSC-derived, 4:3), 1280×720 (HDTV widescreen, 16:9). Uncompressed 640×480 × 24 bits × 30 fps exceeds 200 Mbps — far beyond any office or home link — so compression is mandatory. Interlacing splits each frame into odd and even fields broadcast sequentially (≈60 fields/sec NTSC, 50 PAL); computer video is progressive because graphics buffers eliminate flicker, but playing interlaced video on a computer produces combing near sharp edges. JPEG compresses still images (Y/Cb/Cr color space, 8×8 DCT blocks, quantization table, zigzag run-length, Huffman) at ~10:1 to 20:1. MPEG adds inter-frame redundancy: I-frames (self-contained, JPEG-like), P-frames (macroblock differences vs previous frame, with motion vectors), and B-frames (bidirectional, references past and future frames). MPEG-1 (1993, ~1 Mbps VCR quality), MPEG-2 (1996, 4–8 Mbps DVD/broadcast), MPEG-4 AVC/H.264 (2003, half the bitrate of earlier encoders for the same quality, >50:1 compression, Blu-ray HDTV). AVC encoders are highly asymmetric — slow expensive encoding is fine for a film library but unacceptable for real-time videoconferencing.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python (stdlib)
**Prerequisites:** Lesson 01 (Digital Audio); Phase 2 Nyquist
**Time:** ~70 minutes

## Learning Objectives

- Compute raw uncompressed video bit rate from width × height × bits/pixel × fps, and explain why 640×480 × 24 × 30 exceeds 200 Mbps.
- Distinguish progressive vs interlaced scanning, name the NTSC (29.97), PAL (25), and film (24) frame rates, and explain combing.
- List the JPEG pipeline stages (RGB→YCbCr, 4:2:0 chroma subsample, 8×8 DCT, quantization, zigzag run-length, Huffman) and why luminance gets more bits than chrominance.
- Name the three MPEG frame types (I, P, B), state what each references, and explain why I-frames must appear periodically for multicast, error recovery, and random access.
- Explain why MPEG encoding is asymmetric and why that asymmetry rules out heavy B-frame search for real-time conferencing.

## The Problem

A team is launching a video product and must pick a resolution, frame rate, and codec. They size a 640×480 stream at 24 bits/pixel and 30 fps and discover it needs over 200 Mbps — more than the company's uplink. They need to understand why video compresses so well (spatial and temporal redundancy), what the codec actually does to a frame, and why some encoders are fine for stored movies but unusable for a live call. Without this, they pick the wrong codec, blow the latency budget, or ship artifacts on every scene cut.

## The Concept

### Pixels, frames, and frame rates

The simplest digital video is a sequence of frames, each a rectangular grid of pixels. 1 bit/pixel is black-and-white (awful quality). 8 bits/pixel gives 256 gray levels (good black-and-white). Color uses 8 bits each for R, G, B — 24 bits/pixel, about 16 million colors. On LCD monitors each pixel has closely spaced R/G/B subpixels that the eye blends. The eye retains an image for some milliseconds; drawing 24, 25, or 30 frames/sec produces motion. Standard frame rates: 24 fps (35 mm film), 29.97 fps (NTSC color — reduced from 30 to free bandwidth for color signaling), 25 fps (PAL). Interlacing splits each frame into odd and even scan-line fields, broadcast sequentially for ~60 (NTSC) or 50 (PAL) fields/sec; progressive video does not interlace because computer graphics buffers can redraw at 50–100 Hz. Playing interlaced fast-motion video on a progressive monitor produces combing — short horizontal lines near sharp edges.

### Frame sizes and aspect ratios

| Resolution | Pixels | Aspect | Typical use |
|------------|--------|--------|-------------|
| 320 × 240 | 76,800 | 4:3 | Low-res Internet video |
| 640 × 480 | 307,200 | 4:3 | Full-screen, NTSC-derived |
| 720 × 480 | 345,600 | 4:3 | Standard DVD |
| 1920 × 1080 | 2,073,600 | 16:9 | Blu-ray HDTV |
| 1280 × 720 | 921,600 | 16:9 | HDTV widescreen |

More pixels increase image quality so the picture does not blur when expanded; many monitors show more pixels than HDTV.

### The raw-bitrate problem

A standard 640 × 480 frame at 24 bits/pixel and 30 fps produces 640 × 480 × 24 × 30 = 221,184,000 bps ≈ 221 Mbps. That exceeds nearly every office and home uplink. Uncompressed video over a WAN is impossible; massive compression is the only hope. `code/main.py` computes the raw rate for any resolution and shows the compression ratio needed to hit common target bitrates.

### JPEG: still-image compression

JPEG (Joint Photographic Experts Group, ISO/IEC 10918) compresses continuous-tone still images at 10:1 to 20:1 for natural images. The lossy sequential pipeline:

1. **Color conversion**: RGB → Y (luminance), Cb, Cr (chrominance). The eye is more sensitive to luminance than chrominance, so we can afford to lose chroma detail.
2. **Chroma subsampling**: square blocks of 4 Cb/Cr pixels are averaged, halving chroma data (4:2:0). Lossy but barely noticed.
3. **Block preparation**: subtract 128 from each element; split each matrix into 8×8 blocks (a 640×480 Y matrix yields 4800 blocks; Cb, Cr yield 1200 each).
4. **DCT**: apply a Discrete Cosine Transform to each 8×8 block. Element (0,0) is the block average; other coefficients decay rapidly with distance from origin.
5. **Quantization**: divide each DCT coefficient by a weight from a quantization table. Weights increase sharply from origin, dropping high spatial frequencies. This is where JPEG is lossy; the table is application-supplied and controls the loss/compression trade-off.
6. **Differential coding**: replace each block's (0,0) value with its difference from the previous block's average.
7. **Zigzag run-length**: linearize the 64 elements in a zigzag scan so trailing zeros cluster, then run-length-encode (e.g., 38 consecutive zeros → one count).
8. **Huffman**: assign short codes to common numbers, long codes to rare ones.

Decoding runs the pipeline backward. JPEG is roughly symmetric: decode takes about as long as encode. `assets/digital-video.svg` diagrams the full JPEG pipeline.

### MPEG: inter-frame compression

MPEG (Motion Picture Experts Group) adds temporal redundancy to JPEG's spatial redundancy. Three frame types:

| Frame | Self-contained? | References | Use |
|-------|-----------------|------------|-----|
| I-frame | Yes | None (JPEG-like still) | Random access, error recovery, multicast join |
| P-frame | No | Previous I or P frame | Predictive; macroblock differences + motion vectors |
| B-frame | No | Previous and future I/P frames | Best compression; needs future frames buffered |

I-frames appear periodically (1–2 per second) for three reasons: (1) multicast viewers tuning in at will could not decode anything if all frames depended on the first frame; (2) any frame received in error makes all later frames junk without periodic I-frames to resynchronize; (3) fast-forward/rewind would otherwise require decoding every skipped frame.

P-frames encode inter-frame differences using **macroblocks** — 16×16 pixels of luminance, 8×8 of chrominance. The encoder searches the previous frame for a matching macroblock (the standards do not specify search distance, quality threshold, or algorithm). If found, the macroblock is encoded as a motion vector (Δx, Δy) plus the DCT/quantized/Huffman-coded difference. If not found, it is encoded like an I-frame.

B-frames are similar but can reference macroblocks in either past or future frames, improving motion compensation when objects pass in front of or behind other objects. B-frames give the best compression but require the encoder to hold past, current, and future frames in memory, and decoding is delayed until dependent frames arrive — so B-frames are not always used.

### MPEG standards and compression ratios

| Standard | Year | Target | Typical bitrate |
|----------|------|--------|-----------------|
| MPEG-1 | 1993 | VCR quality, CD storage | ~1 Mbps (40:1) |
| MPEG-2 | 1996 | DVD, digital broadcast (DVB) | 4–8 Mbps |
| MPEG-4 (object-based) | 1999 | Natural + synthetic mixing | varies |
| MPEG-4 AVC / H.264 | 2003 | Half the bitrate of older encoders for same quality | >50:1, Blu-ray HDTV |

### Encoder asymmetry

MPEG encoding is highly asymmetric. An encoder may try every plausible macroblock position in the previous frame to maximize compression — fine for one-time encoding of a film library, terrible for real-time videoconferencing. Each implementation chooses search effort and "found" thresholds; the standard only fixes the decoder interface, allowing implementers to compete on quality and speed. Decoding I-frames is JPEG-like; decoding P-frames requires buffering the previous frame and assembling the new frame macroblock by macroblock.

### Timestamps and audio/video sync

MPEG encoders compress audio and video independently. A single clock outputs timestamps to both encoders; the timestamps propagate to the receiver, which uses them to synchronize audio and video streams. Without this, lip-sync drifts.

## Build It

1. Run `python3 code/main.py` and read the raw-bitrate table for 320×240, 640×480, 720p, and 1080p.
2. Note the compression ratio required to fit a 640×480 stream into 1.5 Mbps and 512 kbps targets.
3. Run the JPEG-block-counter: for a 640×480 Y plane, the program prints 4800 8×8 blocks (and 1200 each for Cb/Cr after 4:2:0 subsampling).
4. Open `assets/digital-video.svg` and trace the JPEG pipeline: RGB → YCbCr → 4:2:0 → 8×8 DCT → quantization → zigzag → Huffman.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Size a video stream | width × height × bits × fps | Raw rate matches manual calc |
| Pick a target bitrate | Compression ratio = raw / target | 221 Mbps → 1.5 Mbps needs ~147:1 |
| Choose I-frame interval | Periodic I-frames 1–2/sec | Supports random access + error recovery |
| Choose codec for live vs stored | Stored: B-frames OK; Live: I/P only | Asymmetry constraint respected |
| Diagnose combing | Interlaced source on progressive display | Artifact explained, deinterlace needed |

## Ship It

Produce `outputs/video-codec-sizing.md`: for a chosen resolution, frame rate, and target bitrate, record the raw rate, required compression ratio, recommended codec (MPEG-2 / AVC), and I-frame interval. Reusable for any future video product sizing.

## Exercises

1. Compute the raw bitrate of 1280×720 × 24 bits × 30 fps. What compression ratio is required to fit into a 5 Mbps stream?
2. Why does NTSC color run at 29.97 fps instead of 30? What would break if a broadcaster ignored the 0.03 fps difference?
3. A multicast viewer joins mid-stream. Explain why the viewer cannot decode until the next I-frame, and why a stream of only P-frames would be useless to them.
4. A real-time videoconferencing encoder disables B-frames. Give two reasons — one computational, one latency-related.
5. Trace an 8×8 block of Y pixels through JPEG: DCT, quantization (with a sharply rising table), zigzag scan, and run-length. How many of the 64 coefficients survive aggressive quantization?
6. A user reports horizontal "combing" during fast-motion playback. Identify the source (interlaced video on progressive display) and state the fix.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Frame rate | "fps" | Frames per second; 24/25/29.97/30 common |
| Interlacing | "fields" | Odd/even scan lines broadcast separately; ~60/50 fields/sec |
| Combing | "jagged edges" | Artifact of interlaced video on progressive display |
| Macroblock | "MPEG unit" | 16×16 luminance / 8×8 chrominance motion-compensation unit |
| I-frame | "key frame" | Self-contained; random access + error recovery point |
| P-frame | "predicted" | Macroblock differences vs previous I/P + motion vectors |
| B-frame | "bidirectional" | References past + future; best compression, needs buffering |
| DCT | "the transform" | Discrete Cosine Transform on 8×8 blocks; (0,0) = block average |
| 4:2:0 | "chroma subsample" | Average 4 Cb/Cr pixels into 1; halves chroma data |
| AVC / H.264 | "modern codec" | MPEG-4 part 10; >50:1 compression; Blu-ray HDTV |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Section 7.4.2 (Digital Video).
- ISO/IEC 10918 — JPEG standard.
- ISO/IEC 11172 — MPEG-1.
- ISO/IEC 13818 — MPEG-2.
- ISO/IEC 14496-10 — MPEG-4 AVC / H.264.
- Sullivan & Wiegand (2005), "Video Compression — From Concepts to H.264/AVC," *MPEG Industry Forum*.
