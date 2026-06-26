# JPEG Image Compression Pipeline

> JPEG (Joint Photographic Experts Group, ISO/IEC 10918-1, finalized 1992) is a *lossy* still-image codec that compresses 24-bit RGB photographs at 10:1 to 20:1 by exploiting two redundancies: psychovisual (the eye is more sensitive to luminance than to chrominance, and to low spatial frequencies than to high), and statistical (Huffman coding of the quantized DCT coefficients). The encoder pipeline is: (1) convert RGB to YCbCr and downsample Cb/Cr by 2:1 in each axis (4:2:0 chroma subsampling), (2) split the image into 8x8 blocks, (3) compute the 8x8 **Discrete Cosine Transform (DCT)** of each block, (4) divide each of the 64 DCT coefficients by a luminance or chrominance **quantization table** and round to integer, (5) **differential pulse-code modulation (DPCM)** encode the DC coefficient, (6) **zigzag scan** the 63 AC coefficients, (7) **run-length encode** the resulting sequence of (run, value) pairs, and (8) **Huffman code** the run-value pairs using a pair of standard tables (one for luminance, one for chrominance). The decoder reverses the steps. A 640x480 24-bit RGB image (921,600 bytes) compresses to 20-90 KB at quality 75/100. The DCT is lossless; the only lossy step is (4) quantization, controlled by the tables and a single quality factor `q` that scales all 64 entries.

**Type:** Learn
**Languages:** Python 3 (stdlib only), grayscale bitmap (PPM/PBM) output
**Prerequisites:** Discrete Fourier transform intuition, basic linear algebra, RGB to YCbCr color conversion
**Time:** ~75 minutes

## Learning Objectives

- Map the JPEG pipeline end to end: color conversion, block split, DCT, quantization, DPCM, zigzag, RLE, Huffman, file format.
- Compute the 8x8 DCT and IDCT from the definition and confirm that round-trip error is below 1e-9.
- Apply a luminance quantization table scaled by a quality factor and show that high-frequency coefficients collapse to zero.
- Walk the zigzag scan order and count trailing zeros that the run-length encoder skips via the (0,0) end-of-block symbol.
- Huffman-encode (run, size) symbols using a standard JPEG table and report the average bits per symbol.
- Decode a JPEG file from its SOI, APP0, DQT, SOF0, DHT, SOS, entropy-coded, EOI segments.

## The Problem

A modern smartphone camera captures 12-megapixel RAW frames at 36 MB. The user wants to email a single photo to a friend, store a thousand photos in 16 GB of flash, or upload a thumbnail to a website. Without compression, none of these are practical. Lossless coders like PNG reach 2:1 on photographs, which is not enough.

JPEG targets 10:1 to 20:1 compression at "visually lossless" quality. The trick is the eye does not see high-frequency chrominance details, so the encoder can throw them away; and the eye does not see low-amplitude high-frequency luminance either, so the encoder can quantize those heavily too. The DCT is the right tool because it decorrelates pixels into spatial frequency components, and the eye's contrast sensitivity function happens to fall off at exactly the rate the DCT coefficients decay, so quantizing aggressively is safe.

## The Concept

### Step 1: Color conversion and 4:2:0 chroma subsampling

The eye has roughly 100 photoreceptors (rods) per cone (cones detect color). Luminance (Y) is preserved at full resolution; chrominance (Cb, Cr) can be cut in half horizontally and vertically. The conversion is:

```
Y  =  0.299  R + 0.587  G + 0.114  B
Cb = -0.169  R - 0.331  G + 0.500  B + 128
Cr =  0.500  R - 0.419  G - 0.081  B + 128
```

(For 8-bit values, the chrominance channels are offset by 128 to keep them unsigned.) After conversion, the Cb and Cr planes are decimated 2:1 in each axis, giving the 4:2:0 format that halves the chroma data without the eye noticing.

### Step 2: 8x8 block decomposition

The image is split into non-overlapping 8x8 blocks. For a 640x480 image, the Y plane gives 4,800 blocks and each chroma plane gives 1,200 blocks (since the chroma planes are 320x240). The block size is the smallest unit at which the DCT makes sense; smaller blocks waste bits on overhead, larger blocks lose too much on a single errored coefficient.

### Step 3: The 8x8 DCT

The forward DCT (FDCT) of an 8x8 block p(x,y) is:

```
F(u,v) = (1/4) C(u) C(v) sum_{x=0..7} sum_{y=0..7}
         p(x,y) cos((2x+1) u pi / 16) cos((2y+1) v pi / 16)
```

with C(0) = 1/sqrt(2) and C(k>0) = 1. The output is an 8x8 matrix of real coefficients. F(0,0) is the average (DC) value of the block, multiplied by 8. F(u,v) for u or v non-zero is the AC content at the corresponding spatial frequency. The DCT is its own inverse (up to a factor of 2 and normalization); the inverse DCT (IDCT) reconstructs p(x,y) from F(u,v). The DCT is mathematically lossless; round-trip error below 1e-9 is expected for double-precision floating point.

### Step 4: Quantization (the only lossy step)

The heart of JPEG. Each of the 64 coefficients is divided by a corresponding entry in a quantization table, then rounded to the nearest integer. The standard luminance table is:

```
16  11  10  16  24  40  51  61
12  12  14  19  26  58  60  55
14  13  16  24  40  57  69  56
14  17  22  29  51  87  80  62
18  22  37  56  68 109 103  77
24  35  55  64  81 104 113  92
49  64  78  87 103 121 120 101
72  92  95  98 112 100 103  99
```

Larger table entries (in the bottom-right) mean more aggressive quantization of high frequencies, which the eye cannot see anyway. The table can be scaled by a quality factor q: when q < 50, the entries are multiplied by 50/q; when q >= 50, the entries are multiplied by (200 - 2q) / 100. q = 75 is the default in most software.

The output of the division is an integer matrix with many trailing zeros (because the bottom-right entries are large). On the textbook 8x8 example, the matrix compresses from 64 floats to 13 nonzero integers plus 51 zeros.

### Step 5: DC differential and AC zigzag

The DC coefficient (top-left) is the block average, and averages change slowly across the image, so JPEG does DPCM on the DC stream: each block stores (its_DC - previous_block_DC). AC coefficients are reordered by a **zigzag scan** that walks the 8x8 matrix from low frequencies to high. The scan concentrates the nonzero values at the start of the 64-coefficient vector and the zeros at the end, where they can be skipped.

### Step 6: Run-length encoding

The (0,0) entry on the zigzag means "end of block." The encoder emits a sequence of (run_length, value) pairs until it reaches (0,0). A run of 16 zeros is encoded as the special symbol ZRL (zero run length). The runs compress long zero runs into a single symbol.

### Step 7: Huffman coding

JPEG defines two standard tables (one for luminance, one for chrominance) of Huffman codes for the (run, size) symbol where size = number of bits needed to encode the value. The (0,0) end-of-block marker has its own short code. After Huffman, the average bits per symbol is 3-6 for natural images; without Huffman, the byte-aligned RLE would be 8 bits per symbol.

### Step 8: File format (JFIF)

A JPEG file is a sequence of **segments**, each beginning with a 2-byte marker (0xFF, then a code). The order is:

| Marker | Meaning |
|---|---|
| 0xFFD8 SOI | Start of image |
| 0xFFE0 APP0 | JFIF identifier, version, density |
| 0xFFDB DQT | Quantization table(s) |
| 0xFFC0 SOF0 | Start of frame: width, height, components, sampling factors |
| 0xFFC4 DHT | Huffman table(s) |
| 0xFFDA SOS | Start of scan: entropy-coded data follows |
| (data) | Compressed image data |
| 0xFFD9 EOI | End of image |

The decoder reads the segments, builds its tables, then decodes the entropy-coded bitstream block by block.

## Build It

`code/main.py` implements the JPEG encoder from the DCT forward and writes a minimal JPEG file. It does not use libjpeg. The pipeline:

1. **Test image.** A 32x32 RGB test pattern with a smooth gradient and a high-frequency checkerboard. The pattern is small so the run is fast and the output is easy to inspect.
2. **RGB to YCbCr.** Applies the BT.601 conversion, shifts Cb/Cr by 128, and downsamples them 2:1 (4:2:0).
3. **Block split.** Slices the Y plane into 8x8 blocks (4,800 for a VGA image; 16 for the test pattern).
4. **DCT.** Computes the 8x8 FDCT from the definition. Verifies reconstruction by computing the IDCT and printing max error.
5. **Quantization.** Divides each coefficient by the standard luminance table scaled by q = 75, rounds to integer, and counts the trailing zeros.
6. **Zigzag + DPCM on DC + RLE on AC.** Produces a sequence of (run, value) symbols terminated by (0, 0).
7. **Huffman.** Uses a small standard luminance table and reports the average bits per symbol.
8. **JFIF writer.** Emits a minimal JPEG byte stream (SOI, APP0, DQT, SOF0, DHT, SOS, entropy-coded data, EOI). The output is written to `outputs/test.jpg` and is decodable by any standard JPEG reader.

Run:

```bash
python3 phases/13-streaming-real-time-media-and-content-delivery/10-jpeg-image-compression-pipeline/code/main.py
```

Expected output:

```text
32x32 RGB test image, raw = 3072 bytes
YCbCr 4:2:0 split: Y 16 blocks, Cb 4 blocks, Cr 4 blocks
DCT round-trip max error: 2.84e-17
Quantized block 0: 13 nonzero / 64 entries
DC DPCM: range -32..+34
Huffman average bits/symbol: 4.31
JFIF output: outputs/test.jpg (decodable)
```

## Use It

| Tool | Mode | Typical use |
|---|---|---|
| `cjpeg -quality 75` (libjpeg) | Lossy | Standard photo compression |
| `jpegoptim --max=85` | Lossless re-compress | Recompress without re-encoding |
| `mozjpeg -quality 80` | Lossy, slow | Better Huffman tables, smaller files |
| `guetzli -quality 90` | Lossy, very slow | Perceptual optimization, 20-30% smaller |
| `jpegtran` | Lossless | Crop/rotate without re-encoding |
| `cwebp -q 80` | WebP | Modern, 30% better than JPEG at the same SSIM |
| `avifenc -q 60` | AV1 Image File | Best modern format, 50% better than JPEG |

For photographs, q = 75-85 is the typical sweet spot. Below q = 50 the 8x8 blocks become visible as ringing near sharp edges. Above q = 95 the file size climbs rapidly with no perceptual gain. The right tool for a thumbnail is WebP or AVIF; JPEG is still the right choice for compatibility.

## Ship It

`outputs/test.jpg` is the JFIF output of the test pattern. Any JPEG reader (Preview, Chrome, GIMP, Pillow) opens it. The JSON report at `outputs/jpeg_report.json` records the per-block statistics, the Huffman code lengths used, and the achieved compression ratio. The SVG diagram in `assets/jpeg-image-compression-pipeline.svg` shows the eight pipeline stages with arrows and labels.

## Exercises

1. **DCT vs DFT.** Compare the 8x8 DCT and the 8x8 DFT of the same block. Confirm that the DCT has no imaginary component and that the magnitudes agree to within 1e-6.
2. **Quality factor sweep.** Run the encoder at q = 10, 25, 50, 75, 95, 100 and plot the output file size and the number of nonzero AC coefficients per block. At what q does the block structure become visible?
3. **Chroma subsampling.** Implement 4:4:4 (no subsampling) and 4:2:2 (horizontal-only) and compare file size and visual quality on a high-frequency chroma test pattern.
4. **Custom quantization table.** Replace the standard luminance table with one that quantizes the bottom-right less aggressively. Confirm that the file size grows and the visible quality improves.
5. **Huffman tables.** Build a Huffman table from the actual symbol frequencies of an image and compare the average bits per symbol against the standard table.
6. **JFIF round-trip.** Decode the JPEG output and confirm that the reconstructed image is within the expected SSIM of the original.

## Key Terms

| Term | Definition |
|---|---|
| DCT | Discrete Cosine Transform; decorrelates pixels into spatial frequencies |
| IDCT | Inverse DCT; reconstructs pixels from DCT coefficients |
| 4:2:0 | Chroma subsampling: Cb and Cr planes at 1/4 the resolution of Y |
| Quantization table | 8x8 matrix that divides each DCT coefficient, with rounding |
| Quality factor | Single scalar `q` (1-100) that scales the quantization table |
| DC coefficient | DCT(0,0); the block's average pixel value |
| AC coefficients | The other 63 DCT coefficients, ordered by zigzag |
| Zigzag scan | The 0..63 permutation that reorders an 8x8 block into a 1D vector |
| DPCM | Differential Pulse-Code Modulation; encoding differences, not absolutes |
| Huffman coding | Variable-length prefix code for symbols with known frequencies |
| JFIF | JPEG File Interchange Format; the common wrapper for JPEG data |
| Baseline JPEG | The mandatory sequential DCT-based mode, defined in ISO/IEC 10918-1 |

## Further Reading

- ISO/IEC 10918-1:1992, "Information technology - Digital compression and coding of continuous-tone still images: Requirements and guidelines."
- ITU-T T.81, "Information technology - Digital compression and coding of continuous-tone still images - Part 1."
- G. K. Wallace, "The JPEG still picture compression standard," Communications of the ACM, vol. 34, no. 4, April 1991.
- W. B. Pennebaker and J. L. Mitchell, *JPEG: Still Image Data Compression Standard*, Springer, 1993.
- A. Skodras, C. Christopoulos, and T. Ebrahimi, "The JPEG 2000 still image compression standard," IEEE Signal Processing Magazine, vol. 18, no. 5, September 2001.
- libjpeg-turbo documentation, https://libjpeg-turbo.org/.
- D. S. Taubman and M. W. Marcellin, *JPEG2000 Image Compression Fundamentals, Standards and Practice*, Springer, 2002.
