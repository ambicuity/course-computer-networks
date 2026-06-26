"""LDPC codes and iterative belief-propagation decoding.

Stdlib-only demo: encode with a (7,4,3) Hamming parity-check matrix,
inject soft errors, and decode with the sum-product (belief-propagation)
algorithm on the Tanner graph.  All math is plain floats / ints, no deps.

Run:  python3 main.py
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 1. The code: parity-check matrix H and generator G (over GF(2)).
#    (7,4,3) Hamming code.  Systematic form: bits 1..4 are data, 5..7 checks.
# ---------------------------------------------------------------------------

H = [
    [1, 1, 1, 0, 1, 0, 0],   # check p1  covers bits 1,2,3,5
    [1, 1, 0, 1, 0, 1, 0],   # check p2  covers bits 1,2,4,6
    [1, 0, 1, 1, 0, 0, 1],   # check p3  covers bits 1,3,4,7
]

# Generator G (4x7) in systematic form: c = m @ G  (mod 2).
# Columns 1..4 = identity (data), columns 5..7 = parity per rows of H.
G = [
    [1, 0, 0, 0, 1, 1, 1],   # m1 -> p1 p2 p3
    [0, 1, 0, 0, 1, 1, 0],   # m2 -> p1 p2
    [0, 0, 1, 0, 1, 0, 1],   # m3 -> p1 p3
    [0, 0, 0, 1, 0, 1, 1],   # m4 -> p2 p3
]

N = len(H[0])          # 7 codeword bits
K = len(G)             # 4 message bits
M = len(H)             # 3 parity checks


# ---------------------------------------------------------------------------
# 2. GF(2) linear-algebra helpers.
# ---------------------------------------------------------------------------

def gf2_matvec(matrix: list[list[int]], vec: list[int]) -> list[int]:
    """Return matrix @ vec over GF(2)."""
    out = []
    for row in matrix:
        acc = 0
        for r, v in zip(row, vec):
            acc ^= (r & v)
        out.append(acc)
    return out


def encode(message: list[int]) -> list[int]:
    """Encode a K-bit message into an N-bit codeword (c = m G mod 2)."""
    if len(message) != K:
        raise ValueError(f"message must be {K} bits, got {len(message)}")
    codeword = []
    for col in range(N):
        bit = 0
        for r in range(K):
            bit ^= (message[r] & G[r][col])
        codeword.append(bit)
    return codeword


def syndrome(word: list[int]) -> list[int]:
    """Syndrome s = H word^T (mod 2).  Zero vector <=> valid codeword."""
    return gf2_matvec(H, word)


def syndrome_weight(word: list[int]) -> int:
    return sum(syndrome(word))


# ---------------------------------------------------------------------------
# 3. Tanner graph construction.
# ---------------------------------------------------------------------------

@dataclass
class TannerGraph:
    bit_neighbors: list[list[int]] = field(default_factory=list)
    check_neighbors: list[list[int]] = field(default_factory=list)


def tanner_graph(h: list[list[int]]) -> TannerGraph:
    g = TannerGraph(
        bit_neighbors=[[] for _ in range(len(h[0]))],
        check_neighbors=[[] for _ in range(len(h))],
    )
    for j, row in enumerate(h):
        for i, val in enumerate(row):
            if val:
                g.bit_neighbors[i].append(j)
                g.check_neighbors[j].append(i)
    return g


# ---------------------------------------------------------------------------
# 4. Channel: hard bits -> soft LLRs.
#    bit 0 -> +1, bit 1 -> -1.  LLR = 2 y / sigma^2  (BPSK over AWGN).
# ---------------------------------------------------------------------------

def inject_flips(codeword: list[int], flip_positions: list[int]) -> list[int]:
    """Return a copy with the named bit positions flipped (hard errors)."""
    r = list(codeword)
    for p in flip_positions:
        r[p] ^= 1
    return r


def hard_llrs(word: list[int], magnitude: float = 6.0) -> list[float]:
    """Convert a hard word to confident LLRs (positive => bit 0)."""
    return [magnitude if b == 0 else -magnitude for b in word]


# ---------------------------------------------------------------------------
# 5. Sum-product belief propagation on the Tanner graph.
#    q[i][j] : message bit i -> check j  (LLR).
#    r[j][i] : message check j -> bit i  (LLR).
# ---------------------------------------------------------------------------

def belief_propagation_decode(
    llr_in: list[float],
    graph: TannerGraph,
    max_iter: int = 20,
) -> tuple[list[int], int, list[dict]]:
    """Decode soft LLRs with sum-product BP. Returns (bits, iters, history)."""
    n = len(graph.bit_neighbors)
    # q[i] is the list of LLRs bit i sends to each of its checks (init = channel LLR)
    q: list[list[float]] = [[llr_in[i] for _ in graph.bit_neighbors[i]] for i in range(n)]

    history: list[dict] = []

    for it in range(1, max_iter + 1):
        # --- Check-node update ---
        # r[j][i] = 2 * atanh( prod_{i' != i} tanh(q[i'][j] / 2) )
        r: list[list[float]] = [
            [0.0 for _ in graph.check_neighbors[j]]
            for j in range(len(graph.check_neighbors))
        ]
        for j, bits in enumerate(graph.check_neighbors):
            prod = 1.0
            tanh_vals: list[float] = []
            for i in bits:
                qpos = graph.bit_neighbors[i].index(j)
                tv = math.tanh(q[i][qpos] / 2.0)
                tanh_vals.append(tv)
                prod *= tv
            for idx, i in enumerate(bits):
                factor = tanh_vals[idx]
                if abs(factor) > 1e-12:
                    excl = prod / factor
                else:
                    excl = 0.0
                # clamp against float drift past +/-1
                excl = max(-1.0 + 1e-12, min(1.0 - 1e-12, excl))
                r[j][idx] = 2.0 * math.atanh(excl)

        # --- Bit-node update ---
        # L(i) = L_ch(i) + sum_j r[j][i];  q[i][j] = L(i) - r[j][i]
        L = [0.0] * n
        for i in range(n):
            total = llr_in[i]
            for j in graph.bit_neighbors[i]:
                rpos = graph.check_neighbors[j].index(i)
                total += r[j][rpos]
            L[i] = total
            for jpos, j in enumerate(graph.bit_neighbors[i]):
                rpos = graph.check_neighbors[j].index(i)
                q[i][jpos] = L[i] - r[j][rpos]

        # --- Hard decision & halt test ---
        bits = [0 if v >= 0 else 1 for v in L]
        sw = syndrome_weight(bits)
        history.append({
            "iter": it,
            "syndrome_weight": sw,
            "llrs": [round(v, 3) for v in L],
            "bits": bits,
        })
        if sw == 0:
            return bits, it, history

    bits = [0 if v >= 0 else 1 for v in L]
    return bits, max_iter, history


# ---------------------------------------------------------------------------
# 6. Pretty-printing and demo.
# ---------------------------------------------------------------------------

def print_word(label: str, word: list[int]) -> None:
    print(f"  {label}: {''.join(str(b) for b in word)}")


def run_demo(message: list[int], flips: list[int], sigma: float, mag: float) -> None:
    print("=" * 64)
    print(f"message  = {''.join(str(b) for b in message)}")
    cw = encode(message)
    print_word("codeword", cw)
    print(f"  syndrome(codeword) = {syndrome(cw)}  (must be all zero)")

    noisy = inject_flips(cw, flips)
    print_word(f"received (flips at {flips})", noisy)
    print(f"  syndrome(received) = {syndrome(noisy)}  weight={syndrome_weight(noisy)}")

    # Soft LLRs: flipped bits get strongly wrong sign; sigma adds channel jitter.
    llr = hard_llrs(noisy, magnitude=mag)
    rng = random.Random(7)
    llr = [v + rng.gauss(0, sigma) for v in llr]
    print(f"  channel LLRs: {[round(v, 2) for v in llr]}")

    graph = tanner_graph(H)
    bits, iters, hist = belief_propagation_decode(llr, graph, max_iter=20)
    status = " (syndrome==0)" if syndrome_weight(bits) == 0 else " (HIT ITER CAP)"
    print(f"\n  BP decoding: stopped in {iters} iter(s){status}")
    print_word("decoded ", bits)
    print_word("original", cw)
    print(f"  CORRECT: {bits == cw}")

    print("\n  per-iteration trace:")
    for h in hist:
        print(f"    iter {h['iter']:2d}  syn_w={h['syndrome_weight']}  "
              f"LLRs={h['llrs']}")
    print()


def main() -> None:
    print("LDPC (7,4,3) Hamming code -- sum-product belief propagation demo")
    print(f"  N={N}  K={K}  M={M}  rate={K/N:.3f}")
    print("  H =")
    for row in H:
        print("    " + " ".join(str(v) for v in row))

    graph = tanner_graph(H)
    print("\n  Tanner graph:")
    for i, checks in enumerate(graph.bit_neighbors):
        print(f"    bit c{i+1} -> checks {[p + 1 for p in checks]}")
    for j, bits in enumerate(graph.check_neighbors):
        print(f"    check p{j+1} -> bits {[c + 1 for c in bits]}")

    print("\n--- Case 1: single-bit error, high confidence ---")
    run_demo(message=[1, 0, 1, 0], flips=[3], sigma=0.3, mag=8.0)

    print("--- Case 2: two-bit error (within distance-3 reach) ---")
    run_demo(message=[0, 1, 1, 0], flips=[1, 5], sigma=0.3, mag=8.0)

    print("--- Case 3: two-bit error, low confidence (may stall) ---")
    run_demo(message=[1, 1, 0, 0], flips=[2, 4], sigma=2.5, mag=3.0)


if __name__ == "__main__":
    main()
