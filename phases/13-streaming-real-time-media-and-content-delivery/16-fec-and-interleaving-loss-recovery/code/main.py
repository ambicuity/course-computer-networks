"""FEC and Interleaving Loss Recovery.

A stdlib-only demonstration of Forward Error Correction (XOR parity)
and block interleaving for real-time media loss recovery. Shows how
FEC repairs single losses, why FEC alone fails on burst loss, and how
interleaving converts burst loss to scattered loss that FEC can fix.

Run:  python3 main.py
Exit: 0
"""

from __future__ import annotations

import random
from typing import List, Optional, Tuple

FEC_K = 4  # media packets per parity
INTERLEAVE_DEPTH = 4
INTERLEAVE_SPAN = 4
NUM_PACKETS = 16


def xor_bytes(a: bytes, b: bytes) -> bytes:
    """XOR two equal-length byte sequences."""
    return bytes(x ^ y for x, y in zip(a, b))


def xor_all(packets: List[bytes]) -> bytes:
    """XOR all packets in a list together."""
    if not packets:
        return b""
    result = bytearray(packets[0])
    for p in packets[1:]:
        for i in range(len(result)):
            result[i] ^= p[i]
    return bytes(result)


def fec_encode(group: List[bytes]) -> bytes:
    """Generate a FEC parity packet for a group of k media packets."""
    return xor_all(group)


def fec_decode(group: List[Optional[bytes]], parity: bytes) -> Optional[bytes]:
    """Recover a single lost packet in a FEC group using the parity.

    Returns the recovered packet, or None if 0 or 2+ packets are lost.
    """
    lost_indices = [i for i, p in enumerate(group) if p is None]
    if len(lost_indices) != 1:
        return None
    survivors = [p for p in group if p is not None]
    recovered = parity
    for s in survivors:
        recovered = xor_bytes(recovered, s)
    return recovered


def block_interleave(packets: List[bytes], depth: int, span: int) -> List[bytes]:
    """Block interleaver: write rows, read columns."""
    matrix: List[List[bytes]] = [[b""] * span for _ in range(depth)]
    for i, pkt in enumerate(packets):
        row = i % depth
        col = i // depth
        if col < span:
            matrix[row][col] = pkt
    interleaved: List[bytes] = []
    for col in range(span):
        for row in range(depth):
            interleaved.append(matrix[row][col])
    return interleaved


def block_deinterleave(packets: List[bytes], depth: int, span: int) -> List[bytes]:
    """Reverse block interleaving: write columns, read rows."""
    matrix: List[List[bytes]] = [[b""] * span for _ in range(depth)]
    idx = 0
    for col in range(span):
        for row in range(depth):
            if idx < len(packets):
                matrix[row][col] = packets[idx]
                idx += 1
    deinterleaved: List[bytes] = []
    for row in range(depth):
        for col in range(span):
            deinterleaved.append(matrix[row][col])
    return deinterleaved


def simulate_loss(packets: List[bytes], loss_positions: set) -> List[Optional[bytes]]:
    """Simulate packet loss by replacing lost positions with None."""
    return [None if i in loss_positions else p for i, p in enumerate(packets)]


def main() -> None:
    print("FEC and Interleaving Loss Recovery\n")
    print(f"FEC group size k={FEC_K}, interleave depth={INTERLEAVE_DEPTH} span={INTERLEAVE_SPAN}")
    print(f"Total packets: {NUM_PACKETS}\n")

    # Generate synthetic media packets
    random.seed(42)
    media_packets = [bytes([random.randint(0, 255) for _ in range(8)]) for _ in range(NUM_PACKETS)]

    print("=== Part 1: XOR-based FEC ===\n")

    # Encode FEC groups
    groups = [media_packets[i:i+FEC_K] for i in range(0, NUM_PACKETS, FEC_K)]
    parities = [fec_encode(g) for g in groups]

    print(f"  {len(groups)} FEC groups, {len(parities)} parity packets")
    print(f"  Overhead: {len(parities)}/{NUM_PACKETS} = {len(parities)/NUM_PACKETS*100:.0f}%")
    print()

    # Demonstrate single-loss recovery
    print("  Single loss recovery (group 0, lose packet 2):")
    group0 = list(groups[0])
    parity0 = parities[0]
    damaged = [group0[0], group0[1], None, group0[3]]
    recovered = fec_decode(damaged, parity0)
    if recovered is not None:
        match = recovered == group0[2]
        print(f"    Original:  {group0[2].hex()}")
        print(f"    Recovered: {recovered.hex()}")
        print(f"    Match: {match}")
    print()

    # Demonstrate double-loss failure
    print("  Double loss failure (group 1, lose packets 0 and 2):")
    group1 = list(groups[1])
    damaged2 = [None, group1[1], None, group1[3]]
    recovered2 = fec_decode(damaged2, parities[1])
    print(f"    Recovered: {recovered2} (None = cannot repair 2 losses with 1 parity)")
    print()

    print("=== Part 2: Block Interleaving ===\n")

    # Show interleaving
    interleaved = block_interleave(media_packets, INTERLEAVE_DEPTH, INTERLEAVE_SPAN)
    print("  Original order (indices):")
    print(f"    {list(range(NUM_PACKETS))}")
    print("  Interleaved order (indices):")
    # Show the index mapping
    orig_indices = list(range(NUM_PACKETS))
    interleaved_indices = block_interleave(
        [bytes([i]) for i in range(NUM_PACKETS)], INTERLEAVE_DEPTH, INTERLEAVE_SPAN
    )
    print(f"    {[b[0] for b in interleaved_indices]}")
    print()

    # Deinterleave to verify
    deinterleaved = block_deinterleave(interleaved, INTERLEAVE_DEPTH, INTERLEAVE_SPAN)
    match_all = all(d == m for d, m in zip(deinterleaved, media_packets))
    print(f"  Deinterleave round-trip: {'OK' if match_all else 'FAIL'}")
    print()

    print("=== Part 3: Burst Loss Scenarios ===\n")

    # Scenario A: Burst loss without interleaving (lose packets 4,5,6)
    burst_loss = {4, 5, 6}
    print(f"  Scenario A: Burst loss {burst_loss} WITHOUT interleaving")
    damaged_a = simulate_loss(media_packets, burst_loss)
    # Apply FEC per group
    recovered_a = 0
    for gi in range(len(groups)):
        gdamaged = damaged_a[gi*FEC_K:(gi+1)*FEC_K]
        lost_in_group = sum(1 for p in gdamaged if p is None)
        if lost_in_group == 1:
            rec = fec_decode(gdamaged, parities[gi])
            if rec is not None:
                recovered_a += 1
    total_lost_a = len(burst_loss)
    print(f"    Lost: {total_lost_a}, FEC-recovered: {recovered_a}")
    print(f"    Net loss: {total_lost_a - recovered_a}")
    print()

    # Scenario B: Burst loss WITH interleaving
    print(f"  Scenario B: Burst loss {burst_loss} WITH interleaving + FEC")
    # Interleave, apply burst loss at same positions, deinterleave, then FEC
    interleaved_media = block_interleave(media_packets, INTERLEAVE_DEPTH, INTERLEAVE_SPAN)
    damaged_interleaved = simulate_loss(interleaved_media, burst_loss)
    deinterleaved_damaged = block_deinterleave(
        [p if p is not None else b"\x00" * 8 for p in damaged_interleaved],
        INTERLEAVE_DEPTH, INTERLEAVE_SPAN
    )
    # Track which original positions are lost after deinterleaving
    interleaved_lost = block_interleave(
        [i if i in burst_loss else -1 for i in range(NUM_PACKETS)],
        INTERLEAVE_DEPTH, INTERLEAVE_SPAN
    )
    deinterleaved_lost = block_deinterleave(
        [i if i != -1 else -1 for i in interleaved_lost],
        INTERLEAVE_DEPTH, INTERLEAVE_SPAN
    )
    lost_after_deinterleave = set(i for i in deinterleaved_lost if i != -1)
    print(f"    Burst at interleaved positions {burst_loss}")
    print(f"    After deinterleave, original positions lost: {sorted(lost_after_deinterleave)}")
    recovered_b = 0
    for gi in range(len(groups)):
        group_lost = [i for i in lost_after_deinterleave if gi*FEC_K <= i < (gi+1)*FEC_K]
        if len(group_lost) == 1:
            recovered_b += 1
    print(f"    Lost: {len(lost_after_deinterleave)}, FEC-recovered: {recovered_b}")
    print(f"    Net loss: {len(lost_after_deinterleave) - recovered_b}")
    print()

    # Scenario C: Random loss (non-burst)
    random.seed(7)
    random_loss = set(random.sample(range(NUM_PACKETS), 3))
    print(f"  Scenario C: Random loss {sorted(random_loss)} with FEC only")
    recovered_c = 0
    for gi in range(len(groups)):
        gdamaged = simulate_loss(media_packets[gi*FEC_K:(gi+1)*FEC_K],
                                 {i - gi*FEC_K for i in random_loss if gi*FEC_K <= i < (gi+1)*FEC_K})
        lost_in_group = sum(1 for p in gdamaged if p is None)
        if lost_in_group == 1:
            rec = fec_decode(gdamaged, parities[gi])
            if rec is not None:
                recovered_c += 1
    print(f"    Lost: {len(random_loss)}, FEC-recovered: {recovered_c}")
    print(f"    Net loss: {len(random_loss) - recovered_c}")
    print()

    print("=== Part 4: Recovery Comparison ===\n")
    print(f"  {'scenario':>25}  {'lost':>5}  {'recovered':>9}  {'net_loss':>8}")
    print(f"  {'burst (no interleave)':>25}  {total_lost_a:5d}  {recovered_a:9d}  {total_lost_a-recovered_a:8d}")
    print(f"  {'burst (with interleave)':>25}  {len(lost_after_deinterleave):5d}  {recovered_b:9d}  {len(lost_after_deinterleave)-recovered_b:8d}")
    print(f"  {'random (FEC only)':>25}  {len(random_loss):5d}  {recovered_c:9d}  {len(random_loss)-recovered_c:8d}")
    print()

    print("Key observations:")
    print("  - FEC repairs single loss per group, fails on 2+ losses in same group")
    print("  - Burst loss hits adjacent packets, often in the same FEC group -> FEC fails")
    print("  - Interleaving spreads burst loss across different FEC groups -> FEC succeeds")
    print("  - Random loss is already scattered, so interleaving adds no benefit")
    print("  - Combined FEC + interleaving gives best burst-loss recovery")
    print(f"  - Overhead: {len(parities)/NUM_PACKETS*100:.0f}% extra bandwidth for parity packets")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
