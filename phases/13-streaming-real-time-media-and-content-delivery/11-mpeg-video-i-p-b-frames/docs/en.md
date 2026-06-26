# MPEG Video: I, P, and B Frames

> Video is not a sequence of independent images. It is a sequence of predictions. MPEG exploits temporal redundancy so that most frames cost a fraction of a full image.

**Type:** Learn
**Languages:** Python, frame analysis
**Prerequisites:** Phase 13 lessons 01-10 (Digital Video, JPEG)
**Time:** ~75 minutes

## Learning Objectives

- Distinguish I-frames, P-frames, and B-frames and their dependencies
- Explain motion estimation and motion-compensated prediction
- Describe the Group of Pictures (GOP) structure and why decode order differs from display order
- Analyze how frame type affects bitrate, latency, and error resilience
- Reason about GOP tradeoffs for streaming vs editing

## The Problem

A 1080p video at 30 fps with JPEG-quality frames would need roughly 30 x 100 KB = 3 MB per second, or 180 MB per minute. That is too much for streaming. But consecutive video frames are almost identical: the background does not change, the speaker shifts slightly, the camera pans. MPEG exploits this temporal redundancy by encoding most frames as differences from nearby frames, not as standalone images. This cuts bitrate by 10x to 50x.

## The Concept

### Three frame types

**I-frame (Intra-coded).** A complete standalone image, compressed like JPEG. No reference to other frames. It is the largest frame type and the only one you can decode without context. I-frames serve as random access points (seek points) and error recovery anchors.

**P-frame (Predictive-coded).** Encodes the difference between the current frame and a previous reference frame (I or P). Uses motion estimation: for each 16x16 macroblock, the encoder searches the reference frame for the best matching block and records a motion vector plus a residual error. P-frames are much smaller than I-frames but cannot be decoded without their reference.

**B-frame (Bidirectionally predictive-coded).** Encodes the difference using both a past and a future reference frame. For each macroblock, the encoder can choose forward prediction, backward prediction, or an interpolated average of both. B-frames are the smallest and most compress efficient, but they introduce display-order dependency: a B-frame at display time T may need a future reference at T+1, so the encoder must buffer and reorder.

### Motion estimation

```text
current frame macroblock (16x16)
        |
        v
search area in reference frame (+/- p pixels)
        |
        v
best matching block -> motion vector (dx, dy)
        |
        v
residual = current block - predicted block
        |
        v
DCT + quantize the residual (like JPEG on the difference)
```

### Group of Pictures (GOP)

A GOP is a sequence starting with an I-frame followed by P and B-frames. A typical pattern:

```text
Display order:  I  B  B  P  B  B  P  B  B  I ...
Decode order:   I  P  B  B  P  B  B  P  B  B  I ...
```

The I-frame is decoded first (even though P comes after it in display order) because the B-frames between I and P depend on both. This reorder is why streaming latency cannot be zero.

A short GOP (e.g., I P I P) gives fast seeking and error recovery but high bitrate. A long GOP (e.g., I B B P B B P B B P B B I) gives low bitrate but slow seeking and more error propagation.

### Tradeoffs

| Property | I-frame | P-frame | B-frame |
|----------|---------|---------|---------|
| Size | Large | Medium | Small |
| Dependency | None | Past ref | Past + future ref |
| Latency | Low | Medium | High (needs future ref) |
| Error resilience | Anchor | Error propagates forward | Error propagates both ways |
| Use case | Keyframe, seek | General prediction | Maximize compression |

## Build It

The script below simulates an MPEG-like encoder on a synthetic video sequence. It demonstrates:

1. Frame generation (a moving object on a static background)
2. I-frame encoding (intra cost = full frame)
3. P-frame encoding with motion estimation (cost = motion vectors + residual)
4. B-frame encoding with bidirectional prediction (cost = minimal residual)
5. GOP structure with display-order vs decode-order reordering
6. Bitrate comparison across frame types

```python
# Core idea (see code/main.py for full implementation)
for frame in gop:
    if frame_type == 'I':
        cost = intra_cost(frame)
    elif frame_type == 'P':
        mv = motion_estimate(frame, ref_past)
        cost = mv_cost + residual_cost(frame, ref_past, mv)
    elif frame_type == 'B':
        mv_f, mv_b = motion_estimate_bi(frame, ref_past, ref_future)
        cost = mv_cost + residual_cost_bi(frame, ...)
```

## Use It

```bash
python3 code/main.py
```

Expected output: a frame-by-frame trace showing frame type, display order, decode order, motion vectors, residual size, and encoded cost. A summary compares the average bitrate of I-only vs I/P vs I/P/B encoding and shows the compression gain from temporal prediction.

## Ship It

- Use the script to explain why seeking to a B-frame is impossible without decoding its references first.
- Change the GOP length and observe the bitrate vs seek-speed tradeoff.
- Introduce a simulated packet loss at a P-frame and show how the error propagates to dependent frames.

## Exercises

1. Set the GOP to all I-frames (I I I I) and compare the bitrate to the I/P/B mix. What is the compression penalty?
2. Increase the motion search range from +/-4 to +/-16 pixels and observe how the motion vector accuracy affects residual cost.
3. Add a scene cut (completely different frame) in the middle of a GOP and show how the P-frame residual spikes.
4. Simulate losing one P-frame and trace which subsequent frames are affected.
5. Reorder a 12-frame GOP from display order to decode order and verify the dependencies are satisfied.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| I-frame | "Keyframe" | An intra-coded frame with no dependencies; the decode anchor and seek point |
| P-frame | "Delta frame" | A predictively coded frame referencing a past I or P frame via motion vectors |
| B-frame | "The small one" | A bidirectionally predicted frame using both past and future references |
| Motion vector | "Movement" | A (dx, dy) offset pointing to the best matching block in the reference frame |
| GOP | "Group of pictures" | A sequence starting with an I-frame, defining the dependency and seek structure |
| Macroblock | "A tile" | A 16x16 pixel region that is the unit of motion estimation |
| Residual | "The error" | The pixel difference between the current block and the motion-compensated prediction |
| Decode order | "Packet order" | The order frames must be decoded in, which differs from display order due to B-frames |

## Further Reading

- [MPEG-1 (ISO/IEC 11172-2)](https://www.iso.org/standard/22411.html) - the original MPEG video standard
- [H.264/AVC overview](https://en.wikipedia.org/wiki/Advanced_Video_Coding) - modern successor with more frame types
- [Video Compression Demo](https://github.com/leandromoreira/video-compression-tests) - practical encoding comparisons
