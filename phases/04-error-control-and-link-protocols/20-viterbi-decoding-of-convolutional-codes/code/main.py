"""
Viterbi decoding of convolutional codes.

Implements the NASA standard rate-1/2, K=7 binary convolutional encoder
(first used on the 1977 Voyager mission, later reused in 802.11) and a
hard-decision Viterbi decoder that recovers the most likely input bit
sequence from a (possibly corrupted) stream of output bit-pairs.

No third-party dependencies; pure standard library. Run:

    python3 main.py
"""

from typing import List, Tuple

# ---------------------------------------------------------------------------
# NASA standard convolutional code (Fig. 3-7 of the textbook).
# Rate 1/2, constraint length K = 7 (six memory registers).
# Generator polynomials, in octal, as used in 802.11:
#     G0 = 171 (octal) -> 1111001
#     G1 = 133 (octal) -> 1011011
# Bit 0 of these masks taps the *current* input bit; the remaining bits
# tap the shift-register contents s1..s6 (s1 most recent).
# ---------------------------------------------------------------------------

G0 = 0b1111001   # 0o171
G1 = 0b1011011   # 0o133
K = 7            # constraint length (1 input bit + 6 memory bits)


def parity(x: int) -> int:
    """Return 1 if integer x has odd Hamming weight, else 0."""
    return bin(x).count("1") & 1


def encode(bits: List[int]) -> List[Tuple[int, int]]:
    """Encode input bits with the NASA K=7 rate-1/2 code.

    The shift register starts cleared. Each input bit produces a pair
    (output0, output1). To flush the encoder so the final bits stop
    affecting future output, callers should append K-1 = 6 zero tail bits.
    """
    # `state` holds the K-1 = 6 previous input bits, with the most recent
    # input in bit 0 (low bit). When a new bit `b` arrives the 7-bit tap
    # window is (b, state...) with b at bit (K-1); the new state shifts
    # b into bit 0 and drops the oldest bit.
    state = 0
    out: List[Tuple[int, int]] = []
    for b in bits:
        window = ((b & 1) << (K - 1)) | state
        o0 = parity(window & G0)
        o1 = parity(window & G1)
        out.append((o0, o1))
        state = (window >> 1) & ((1 << (K - 1)) - 1)
    return out


# ---------------------------------------------------------------------------
# Trellis: for every state (0..63) and every input bit (0/1), precompute
#   next_state, expected_output_pair.
# A "state" is the 6-bit memory content (the previous 6 input bits), so
# 2^(K-1) = 64 states.
# ---------------------------------------------------------------------------

State = int


def build_trellis() -> List[List[Tuple[State, Tuple[int, int]]]]:
    """trellis[state][input] = (next_state, expected_output_pair)."""
    trell: List[List[Tuple[State, Tuple[int, int]]]] = []
    for state in range(1 << (K - 1)):
        row: List[Tuple[State, Tuple[int, int]]] = []
        for b in (0, 1):
            # 7-bit window: b at the top (bit K-1), then the 6 memory bits.
            window = ((b & 1) << (K - 1)) | state
            o0 = parity(window & G0)
            o1 = parity(window & G1)
            # New memory: shift b in at bit 0, drop the oldest bit.
            next_state = (window >> 1) & ((1 << (K - 1)) - 1)
            row.append((next_state, (o0, o1)))
        trell.append(row)
    return trell


_TRELLIS = build_trellis()


def _hamming(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    """Hamming distance between two bit-pairs (hard-decision metric)."""
    return (a[0] ^ b[0]) + (a[1] ^ b[1])


def viterbi_decode(pairs: List[Tuple[int, int]]) -> Tuple[List[int], int]:
    """Hard-decision Viterbi decode of a received bit-pair stream.

    Returns (decoded_bits, total_path_metric). Assumes the encoder
    started in the all-zero state (standard practice for a coded frame)
    and that the stream includes the K-1 zero tail bits used to flush.
    """
    n_states = 1 << (K - 1)
    INF = 1 << 30
    # dp[state] = (cumulative_metric, back_pointer_state, input_bit)
    dp: List[Tuple[int, State, int]] = [(INF, -1, 0)] * n_states
    dp[0] = (0, -1, 0)  # encoder starts cleared

    history: List[List[Tuple[int, State, int]]] = []

    for received in pairs:
        new_dp: List[Tuple[int, State, int]] = [(INF, -1, 0)] * n_states
        for state in range(n_states):
            cur_metric, _, _ = dp[state]
            if cur_metric >= INF:
                continue
            for b in (0, 1):
                next_state, expected = _TRELLIS[state][b]
                step = _hamming(expected, received)
                cand = cur_metric + step
                if cand < new_dp[next_state][0]:
                    new_dp[next_state] = (cand, state, b)
        history.append(new_dp)
        dp = new_dp

    # Force termination in state 0 (zero-tail flushing guarantees this in
    # a well-formed frame; clamping to 0 also tolerates truncated streams).
    best_state = 0
    best_metric = dp[best_state][0]

    bits: List[int] = []
    cur = best_state
    for snap in reversed(history):
        _, prev, b = snap[cur]
        bits.append(b)
        cur = prev
    bits.reverse()
    return bits, best_metric


# ---------------------------------------------------------------------------
# Demonstration: encode a message, inject errors, decode, and report.
# ---------------------------------------------------------------------------

def _bits_from_str(text: str) -> List[int]:
    out: List[int] = []
    for ch in text.encode("ascii"):
        for i in range(7, -1, -1):
            out.append((ch >> i) & 1)
    return out


def _str_from_bits(bits: List[int]) -> str:
    chars: List[int] = []
    for i in range(0, len(bits) - 7, 8):
        b = 0
        for j in range(8):
            b = (b << 1) | bits[i + j]
        chars.append(b)
    return bytes(chars).decode("ascii", errors="replace")


def main() -> None:
    message = "NET"
    info_bits = _bits_from_str(message)
    tail = [0] * (K - 1)              # flush encoder back to state 0
    tx_bits = info_bits + tail

    encoded = encode(tx_bits)

    print("=== NASA rate-1/2 K=7 convolutional code ===")
    print(f"Message           : {message!r}")
    print(f"Info bits ({len(info_bits)}) : {''.join(map(str, info_bits))}")
    print(f"Tail bits ({len(tail)})  : {''.join(map(str, tail))}")
    print(f"Encoded pairs ({len(encoded)}): "
          + ' '.join(f"{p[0]}{p[1]}" for p in encoded))

    # Clean decode (no errors) -- should recover the message exactly.
    clean_bits, clean_metric = viterbi_decode(encoded)
    print("\n--- Clean channel ---")
    print(f"Path metric       : {clean_metric}")
    print(f"Decoded info      : {_str_from_bits(clean_bits[:len(info_bits)])!r}")

    # Inject three bit errors scattered across the stream.
    corrupted = [list(p) for p in encoded]
    for idx in (3, 11, 19):
        corrupted[idx][0] ^= 1      # flip first bit of that pair
    rx_pairs = [tuple(p) for p in corrupted]
    print("\n--- Channel with 3 bit errors ---")
    flipped = [i for i, (a, b) in enumerate(zip(encoded, rx_pairs)) if a != b]
    print(f"Corrupted pair idx: {flipped}")

    dec_bits, dec_metric = viterbi_decode(rx_pairs)
    print(f"Path metric       : {dec_metric}")
    print(f"Decoded info      : {_str_from_bits(dec_bits[:len(info_bits)])!r}")

    recovered = _str_from_bits(dec_bits[:len(info_bits)])
    print(f"\nErrors corrected? : {recovered == message}")

    # Show a tiny 4-state (K=3) trellis snippet for intuition.
    print("\n=== Mini trellis (K=3, 4 states) for illustration ===")
    print("state | in=0 -> (next,out) | in=1 -> (next,out)")
    small_g0, small_g1, small_k = 0b111, 0b101, 3
    for state in range(1 << (small_k - 1)):
        cells = []
        for b in (0, 1):
            window = ((b << (small_k - 1)) | state) & ((1 << small_k) - 1)
            o0 = parity(window & small_g0)
            o1 = parity(window & small_g1)
            nxt = (window >> 1) & ((1 << (small_k - 1)) - 1)
            cells.append(f"({nxt},{o0}{o1})")
        print(f"  {state:02b}   |       {cells[0]:10s}   |       {cells[1]}")


if __name__ == "__main__":
    main()
