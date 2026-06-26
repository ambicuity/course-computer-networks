"""MPEG Video: I, P, and B Frames.

A stdlib-only simulation of MPEG inter-frame prediction. Demonstrates
I-frames (intra-coded), P-frames (forward predictive), and B-frames
(bidirectionally predictive) with motion estimation, residual cost,
GOP structure, display-order vs decode-order reordering, and bitrate
comparison across frame type mixes.

Uses synthetic video frames (a moving block on a static background).

Run:  python3 main.py
Exit: 0
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

WIDTH = 32
HEIGHT = 32
BLOCK = 16
SEARCH_RANGE = 4
NUM_FRAMES = 12


@dataclass
class Frame:
    """A simple 2D frame of integer pixel values."""
    data: List[List[int]]
    width: int = WIDTH
    height: int = HEIGHT


@dataclass
class EncodedFrame:
    """Result of encoding one frame: type, cost, motion vectors, dependencies."""
    frame_type: str
    display_idx: int
    decode_idx: int
    cost: int
    motion_vectors: List[Tuple[int, int, int, int]] = field(default_factory=list)
    references: List[int] = field(default_factory=list)


def make_frame_with_moving_object(step: int) -> Frame:
    """Generate a frame with a bright block moving diagonally across a dark background."""
    data = [[0 for _ in range(WIDTH)] for _ in range(HEIGHT)]
    obj_x = 4 + step
    obj_y = 4 + step
    for y in range(obj_y, min(obj_y + BLOCK, HEIGHT)):
        for x in range(obj_x, min(obj_x + BLOCK, WIDTH)):
            data[y][x] = 200
    return Frame(data=data)


def sad(block_a: List[List[int]], block_b: List[List[int]]) -> int:
    """Sum of Absolute Differences between two equally-sized blocks."""
    total = 0
    for y in range(len(block_a)):
        for x in range(len(block_a[0])):
            total += abs(block_a[y][x] - block_b[y][x])
    return total


def get_block(frame: Frame, x: int, y: int, size: int = BLOCK) -> List[List[int]]:
    """Extract a size x size block from the frame, clamping to edges."""
    block = []
    for dy in range(size):
        row = []
        for dx in range(size):
            fy = min(max(y + dy, 0), frame.height - 1)
            fx = min(max(x + dx, 0), frame.width - 1)
            row.append(frame.data[fy][fx])
        block.append(row)
    return block


def motion_estimate(
    current: Frame, reference: Frame, mb_x: int, mb_y: int, search: int = SEARCH_RANGE
) -> Tuple[int, int, int]:
    """Find the best matching block in the reference frame. Returns (dx, dy, sad)."""
    cur_block = get_block(current, mb_x, mb_y)
    best_dx = 0
    best_dy = 0
    best_sad = float("inf")
    for dy in range(-search, search + 1):
        for dx in range(-search, search + 1):
            ref_x = mb_x + dx
            ref_y = mb_y + dy
            if ref_x < 0 or ref_y < 0:
                continue
            if ref_x + BLOCK > WIDTH or ref_y + BLOCK > HEIGHT:
                continue
            ref_block = get_block(reference, ref_x, ref_y)
            s = sad(cur_block, ref_block)
            if s < best_sad:
                best_sad = s
                best_dx = dx
                best_dy = dy
    return (best_dx, best_dy, int(best_sad))


def intra_cost(frame: Frame) -> int:
    """Estimate I-frame cost: sum of all pixel values (standalone encoding)."""
    total = 0
    for y in range(0, HEIGHT, BLOCK):
        for x in range(0, WIDTH, BLOCK):
            block = get_block(frame, x, y)
            for row in block:
                for v in row:
                    total += abs(v)
    return total


def p_frame_cost(current: Frame, reference: Frame) -> Tuple[int, List[Tuple[int, int, int, int]]]:
    """Estimate P-frame cost: motion vector bits + residual SAD."""
    total = 0
    mvs: List[Tuple[int, int, int, int]] = []
    for mb_y in range(0, HEIGHT, BLOCK):
        for mb_x in range(0, WIDTH, BLOCK):
            dx, dy, s = motion_estimate(current, reference, mb_x, mb_y)
            mv_cost = 4  # 2 bits per axis, rough
            total += mv_cost + s
            mvs.append((mb_x, mb_y, dx, dy))
    return (total, mvs)


def b_frame_cost(
    current: Frame, ref_past: Frame, ref_future: Frame
) -> Tuple[int, List[Tuple[int, int, int, int]]]:
    """Estimate B-frame cost: best of forward, backward, or interpolated prediction."""
    total = 0
    mvs: List[Tuple[int, int, int, int]] = []
    for mb_y in range(0, HEIGHT, BLOCK):
        for mb_x in range(0, WIDTH, BLOCK):
            cur_block = get_block(current, mb_x, mb_y)
            dx_f, dy_f, sad_f = motion_estimate(current, ref_past, mb_x, mb_y)
            dx_b, dy_b, sad_b = motion_estimate(current, ref_future, mb_x, mb_y)
            # Interpolated prediction (average of past and future)
            ref_past_block = get_block(ref_past, mb_x + dx_f, mb_y + dy_f)
            ref_future_block = get_block(ref_future, mb_x + dx_b, mb_y + dy_b)
            sad_i = 0
            for y in range(BLOCK):
                for x in range(BLOCK):
                    avg = (ref_past_block[y][x] + ref_future_block[y][x]) // 2
                    sad_i += abs(cur_block[y][x] - avg)
            best = min(sad_f, sad_b, sad_i)
            total += 4 + best
            mvs.append((mb_x, mb_y, dx_f, dy_b))
    return (total, mvs)


def build_gop_display_order(frames: List[Frame]) -> List[str]:
    """Assign frame types for a standard IBP GOP pattern."""
    n = len(frames)
    types: List[str] = []
    for i in range(n):
        if i == 0 or i == n - 1:
            types.append("I")
        elif i % 3 == 0:
            types.append("P")
        else:
            types.append("B")
    return types


def reorder_for_decode(display_types: List[str]) -> List[int]:
    """Compute decode order from display order. B-frames move after their references."""
    n = len(display_types)
    decode_order = list(range(n))
    # Simple reorder: move each B-frame right after its preceding P/I reference
    # For IBP pattern: I B B P B B P B B P B B I
    # Decode: I P B B P B B P B B P B B I (P decoded before its B's)
    result: List[int] = []
    used = [False] * n
    for i in range(n):
        if used[i]:
            continue
        if display_types[i] == "B":
            continue
        result.append(i)
        used[i] = True
        # Emit B-frames that follow this reference
        for j in range(i + 1, n):
            if display_types[j] == "B" and not used[j]:
                # Check that the future reference also exists
                result.append(j)
                used[j] = True
            else:
                break
    # Any remaining frames
    for i in range(n):
        if not used[i]:
            result.append(i)
    return result


def main() -> None:
    print("MPEG Video: I, P, and B Frames\n")
    print(f"Frame size: {WIDTH}x{HEIGHT}, macroblock: {BLOCK}x{BLOCK}")
    print(f"Search range: +/-{SEARCH_RANGE} pixels, frames: {NUM_FRAMES}\n")

    # Generate synthetic video
    frames = [make_frame_with_moving_object(i) for i in range(NUM_FRAMES)]

    # Assign frame types
    display_types = build_gop_display_order(frames)
    print("Display order frame types:")
    print(f"  {'idx':>3}  {'type':>4}")
    for i, t in enumerate(display_types):
        print(f"  {i:3d}  {t:>4}")
    print()

    # Compute decode order
    decode_order = reorder_for_decode(display_types)
    print("Decode order (indices):")
    print(f"  {decode_order}")
    decode_types = [display_types[i] for i in decode_order]
    print(f"  Types: {decode_types}\n")

    # Encode each frame
    encoded: List[EncodedFrame] = []
    for display_idx in range(NUM_FRAMES):
        ftype = display_types[display_idx]
        frame = frames[display_idx]

        if ftype == "I":
            cost = intra_cost(frame)
            encoded.append(EncodedFrame("I", display_idx, 0, cost, references=[]))
        elif ftype == "P":
            # Find nearest past I or P
            ref_idx = display_idx - 1
            while ref_idx >= 0 and display_types[ref_idx] == "B":
                ref_idx -= 1
            cost, mvs = p_frame_cost(frame, frames[ref_idx])
            encoded.append(EncodedFrame("P", display_idx, 0, cost, motion_vectors=mvs, references=[ref_idx]))
        elif ftype == "B":
            # Find past and future references
            past_idx = display_idx - 1
            while past_idx >= 0 and display_types[past_idx] == "B":
                past_idx -= 1
            future_idx = display_idx + 1
            while future_idx < NUM_FRAMES and display_types[future_idx] == "B":
                future_idx += 1
            if future_idx >= NUM_FRAMES:
                future_idx = NUM_FRAMES - 1
            cost, mvs = b_frame_cost(frame, frames[past_idx], frames[future_idx])
            encoded.append(EncodedFrame("B", display_idx, 0, cost, motion_vectors=mvs, references=[past_idx, future_idx]))

    # Assign decode indices
    for di, display_idx in enumerate(decode_order):
        encoded[display_idx].decode_idx = di

    # Report
    print("Encoded frame costs:")
    print(f"  {'disp':>4}  {'type':>4}  {'decode':>6}  {'cost':>8}  {'refs':>10}  {'#mvs':>4}")
    for ef in sorted(encoded, key=lambda e: e.display_idx):
        refs_str = ",".join(str(r) for r in ef.references) if ef.references else "-"
        print(f"  {ef.display_idx:4d}  {ef.frame_type:>4}  {ef.decode_idx:6d}  {ef.cost:8d}  {refs_str:>10}  {len(ef.motion_vectors):4d}")
    print()

    # Bitrate comparison
    i_cost = sum(e.cost for e in encoded if e.frame_type == "I")
    p_cost = sum(e.cost for e in encoded if e.frame_type == "P")
    b_cost = sum(e.cost for e in encoded if e.frame_type == "B")
    total = i_cost + p_cost + b_cost
    print("Cost breakdown by frame type:")
    print(f"  I-frames: {i_cost:>8d}  ({len([e for e in encoded if e.frame_type=='I'])} frames)")
    print(f"  P-frames: {p_cost:>8d}  ({len([e for e in encoded if e.frame_type=='P'])} frames)")
    print(f"  B-frames: {b_cost:>8d}  ({len([e for e in encoded if e.frame_type=='B'])} frames)")
    print(f"  Total:    {total:>8d}\n")

    # Compare with all-I encoding
    all_i_cost = sum(intra_cost(f) for f in frames)
    print("Bitrate comparison:")
    print(f"  All I-frames:           {all_i_cost:>8d}  (baseline)")
    print(f"  I/P/B mix:              {total:>8d}  ({100*total/all_i_cost:.0f}% of all-I)")
    print(f"  Compression from temporal prediction: {all_i_cost/max(1,total):.1f}x\n")

    # Motion vector sample
    p_frames = [e for e in encoded if e.frame_type == "P"]
    if p_frames:
        pf = p_frames[0]
        print(f"Sample motion vectors (P-frame at display {pf.display_idx}):")
        for mb_x, mb_y, dx, dy in pf.motion_vectors[:4]:
            print(f"  macroblock ({mb_x},{mb_y}): mv=({dx},{dy})")
    print()

    # Error propagation demo
    print("Error propagation demo (lose P-frame at display idx 3):")
    lost_idx = 3
    affected: List[int] = []
    for ef in encoded:
        if lost_idx in ef.references:
            affected.append(ef.display_idx)
    print(f"  Frames directly depending on lost frame {lost_idx}: {affected}")
    print(f"  Those frames' dependents may also be affected (cascading).\n")

    print("Done. All MPEG frame type demonstrations completed.")


if __name__ == "__main__":
    main()
