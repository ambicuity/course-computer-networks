"""Synchronous CDMA channel simulator with Walsh-Hadamard chip sequences.

This module demonstrates Code Division Multiple Access (CDMA) the way
Tanenbaum presents it in "Computer Networks" Sec. 2.5.5: each station is
assigned an orthogonal m-chip code, transmits its code for a 1 bit, the
negation of its code for a 0 bit, or stays silent. All transmissions add
linearly on the shared medium (voltages superimpose), and a receiver
recovers one station's bit stream by taking the normalized inner product
of the received chip vector with that station's known code.

The orthogonality of the codes (S . T = 0 for distinct codes) is what makes
recovery possible: when the receiver correlates against station C's code,
every other station's contribution cancels and only C's bit survives.

Codes here are generated as Walsh codes via the Hadamard recursion, which
yields 2**n mutually orthogonal sequences of length 2**n. The same family
of codes is used for the channelization (OVSF) codes in real IS-95 / cdmaOne
and WCDMA systems.

Run:  python3 main.py
No third-party dependencies. Pure standard library.
"""

from __future__ import annotations

from typing import Dict, List, Optional

# Bipolar chip alphabet: a chip is either +1 or -1.
HIGH = 1
LOW = -1
SILENT = 0  # a station that transmits nothing during a bit time


def hadamard(order_log2: int) -> List[List[int]]:
    """Build a 2**order_log2 Walsh-Hadamard matrix in bipolar (+/-1) form.

    H(0) = [[1]]; H(n) = [[H(n-1), H(n-1)], [H(n-1), -H(n-1)]].
    Every pair of distinct rows is orthogonal, so the rows are valid CDMA
    chip sequences.
    """
    if order_log2 < 0:
        raise ValueError("order_log2 must be >= 0")
    matrix: List[List[int]] = [[1]]
    for _ in range(order_log2):
        size = len(matrix)
        bigger: List[List[int]] = []
        for row in matrix:
            bigger.append(row + row)            # top-left, top-right
        for row in matrix:
            bigger.append(row + [-c for c in row])  # bottom-left, bottom-right
        matrix = bigger
    return matrix


def normalized_inner_product(a: List[int], b: List[int]) -> float:
    """Compute (1/m) * sum(a_i * b_i), the normalized correlation."""
    if len(a) != len(b):
        raise ValueError("chip vectors must be the same length")
    m = len(a)
    return sum(x * y for x, y in zip(a, b)) / m


def assert_orthogonal(codes: Dict[str, List[int]]) -> None:
    """Verify pairwise orthogonality and unit self-correlation."""
    names = list(codes)
    for i, name_i in enumerate(names):
        self_dot = normalized_inner_product(codes[name_i], codes[name_i])
        if abs(self_dot - 1.0) > 1e-9:
            raise AssertionError(f"{name_i}.{name_i} = {self_dot}, expected 1")
        for name_j in names[i + 1:]:
            cross = normalized_inner_product(codes[name_i], codes[name_j])
            if abs(cross) > 1e-9:
                raise AssertionError(
                    f"{name_i}.{name_j} = {cross}, expected 0 (not orthogonal)"
                )


def encode_bit(code: List[int], bit: Optional[int]) -> List[int]:
    """Map a logical bit to a transmitted chip vector.

    bit == 1   -> the station's chip sequence
    bit == 0   -> the negation of the chip sequence
    bit is None -> silence (all zeros)
    """
    if bit is None:
        return [SILENT] * len(code)
    if bit == 1:
        return list(code)
    if bit == 0:
        return [-c for c in code]
    raise ValueError("bit must be 0, 1, or None")


def channel_sum(transmissions: List[List[int]]) -> List[int]:
    """Add bipolar chip vectors chip-by-chip: the shared-medium superposition."""
    if not transmissions:
        raise ValueError("no transmissions to sum")
    width = len(transmissions[0])
    total = [0] * width
    for tx in transmissions:
        if len(tx) != width:
            raise ValueError("all transmissions must have equal chip width")
        for i, chip in enumerate(tx):
            total[i] += chip
    return total


def recover_bit(received: List[int], code: List[int]) -> Optional[int]:
    """Decode one station's bit from the summed channel signal.

    Returns 1, 0, or None (silent) based on the normalized inner product
    against the target station's code. In a noiseless synchronous system
    the result is exactly +1, -1, or 0.
    """
    score = normalized_inner_product(received, code)
    if abs(score - 1.0) < 1e-9:
        return 1
    if abs(score + 1.0) < 1e-9:
        return 0
    if abs(score) < 1e-9:
        return None
    # Non-integer result => interference / lost synchronization.
    raise ValueError(f"ambiguous correlation {score}; codes not orthogonal?")


def simulate_bit_time(
    codes: Dict[str, List[int]], bits: Dict[str, Optional[int]]
) -> Dict[str, object]:
    """Simulate one synchronized bit time and recover every station's bit."""
    transmissions = [encode_bit(codes[name], bits[name]) for name in codes]
    received = channel_sum(transmissions)
    recovered = {name: recover_bit(received, codes[name]) for name in codes}
    return {"received": received, "recovered": recovered}


def fmt(bit: Optional[int]) -> str:
    return "-" if bit is None else str(bit)


def main() -> None:
    # Four stations, m = 4 chips/bit, Walsh codes of length 4.
    rows = hadamard(2)  # 4 orthogonal sequences of length 4
    # Row 0 is all +1 (the DC code); skip it so silence is distinguishable.
    names = ["A", "B", "C", "D"]
    codes: Dict[str, List[int]] = {name: rows[i] for i, name in enumerate(names)}

    print("=== Walsh chip sequences (m = 4 chips/bit) ===")
    for name, code in codes.items():
        print(f"  {name} = {code}")
    assert_orthogonal(codes)
    print("  [ok] all codes pairwise orthogonal, self-correlation = 1\n")

    scenarios = [
        ("Only C sends a 1", {"A": None, "B": None, "C": 1, "D": None}),
        ("B and C both send 1", {"A": None, "B": 1, "C": 1, "D": None}),
        ("A=1, B=0, C=1 collide", {"A": 1, "B": 0, "C": 1, "D": None}),
        ("All four active", {"A": 1, "B": 0, "C": 1, "D": 0}),
    ]

    for label, bits in scenarios:
        result = simulate_bit_time(codes, bits)
        sent = " ".join(f"{n}={fmt(bits[n])}" for n in names)
        recv = result["received"]
        got = result["recovered"]
        decoded = " ".join(f"{n}={fmt(got[n])}" for n in names)
        match = "OK" if got == bits else "MISMATCH"
        print(f"--- {label} ---")
        print(f"  sent      : {sent}")
        print(f"  on channel: {recv}")
        print(f"  recovered : {decoded}   [{match}]\n")

    # Show the recovery math for station C in the colliding case.
    print("=== Recovery math for station C (A=1, B=0, C=1) ===")
    bits = {"A": 1, "B": 0, "C": 1, "D": None}
    txs = [encode_bit(codes[n], bits[n]) for n in names]
    s = channel_sum(txs)
    score = normalized_inner_product(s, codes["C"])
    print(f"  S = A + B_bar + C = {s}")
    print(f"  S . C = {score:+.0f}  -> bit {recover_bit(s, codes['C'])}")
    print("  Other stations cancel because A.C = B.C = D.C = 0.")


if __name__ == "__main__":
    main()
