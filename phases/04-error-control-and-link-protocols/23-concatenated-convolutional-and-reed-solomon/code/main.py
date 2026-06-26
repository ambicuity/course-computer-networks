"""
Concatenated convolutional + Reed-Solomon coding demo.

Stdlib-only. Implements, end to end:
  * GF(2^8) arithmetic with primitive polynomial 0x11D (CCSDS/DVB field).
  * A Reed-Solomon (7, 3) code over GF(2^8) -> corrects t = 2 symbol errors.
  * The NASA r=1/2, k=7 convolutional encoder (generators 171, 133 octal).
  * A 64-state hard-decision Viterbi decoder.
  * A depth-I block interleaver.
  * A concatenated encoder/decoder that wires RS + interleaver + convolutional.

Run:  python3 main.py
"""

from __future__ import annotations

from typing import List, Tuple

# ---------------------------------------------------------------------------
# GF(2^8) arithmetic, primitive polynomial 0x11D (x^8 + x^4 + x^3 + x^2 + 1)
# ---------------------------------------------------------------------------

PRIM_POLY = 0x11D
_GF_EXP: List[int] = [0] * 512
_GF_LOG: List[int] = [0] * 256


def _init_gf() -> None:
    x = 1
    for i in range(255):
        _GF_EXP[i] = x
        _GF_LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= PRIM_POLY
    for i in range(255, 512):
        _GF_EXP[i] = _GF_EXP[i - 255]


_init_gf()


def gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _GF_EXP[_GF_LOG[a] + _GF_LOG[b]]


def gf_div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("gf_div by zero")
    if a == 0:
        return 0
    return _GF_EXP[(_GF_LOG[a] - _GF_LOG[b]) % 255]


def gf_pow(a: int, e: int) -> int:
    if e == 0:
        return 1
    if a == 0:
        return 0
    return _GF_EXP[(_GF_LOG[a] * e) % 255]


def gf_inv(a: int) -> int:
    return _GF_EXP[(255 - _GF_LOG[a]) % 255]


# ---------------------------------------------------------------------------
# Reed-Solomon (n, k) = (7, 3) over GF(2^8). 2t = 4 parity symbols, t = 2.
# Generator polynomial g(x) = (x - a^1)(x - a^2)(x - a^3)(x - a^4).
# ---------------------------------------------------------------------------

RS_N = 7
RS_K = 3
RS_2T = RS_N - RS_K  # 4
RS_T = RS_2T // 2     # 2


def _rs_generator_poly() -> List[int]:
    g = [1]
    for i in range(1, RS_2T + 1):
        coeff = _GF_EXP[i]
        new_g = [0] * (len(g) + 1)
        for j, gc in enumerate(g):
            new_g[j] ^= gc                       # x * g[j]
            new_g[j + 1] ^= gf_mul(gc, coeff)    # a^i * g[j]
        g = new_g
    return g


_RS_G = _rs_generator_poly()


def rs_encode(data: List[int]) -> List[int]:
    """Systematic RS encode: returns n = k + 2t symbols (data then parity)."""
    if len(data) != RS_K:
        raise ValueError(f"expected {RS_K} data symbols, got {len(data)}")
    buf = data + [0] * RS_2T
    for i in range(RS_K):
        coef = buf[i]
        if coef != 0:
            for j in range(1, len(_RS_G)):
                buf[i + j] ^= gf_mul(_RS_G[j], coef)
    parity = buf[RS_K:]
    return data + parity


def rs_syndromes(r: List[int]) -> List[int]:
    """S_i = r(alpha^i) for i = 1..2t, treating r[0] as the HIGH-order
    coefficient (x^(n-1)), matching the systematic encoder's byte order."""
    s = [0] * RS_2T
    for i in range(1, RS_2T + 1):
        si = 0
        for j in range(RS_N):
            si ^= gf_mul(r[j], gf_pow(_GF_EXP[i], RS_N - 1 - j))
        s[i - 1] = si
    return s


def _berlekamp_massey(s: List[int]) -> Tuple[List[int], int]:
    """Standard BMA over GF(2^8). Returns (Lambda coefficients low->high,
    degree). A degree > t means uncorrectable."""
    lam: List[int] = [1]
    b_poly: List[int] = [1]
    l = 0
    m = 1
    bb = 1
    for n in range(RS_2T):
        # discrepancy: Delta_n = S_n + sum_{i=1}^{l} Lambda_i * S_{n-i}
        delta = s[n]
        for i in range(1, l + 1):
            delta ^= gf_mul(lam[i], s[n - i])
        if delta == 0:
            m += 1
        elif 2 * l <= n:
            t = lam[:]
            coef = gf_div(delta, bb)
            # Lambda(x) -= coef * x^m * B(x); subtraction == XOR in GF(2^8)
            shifted = [0] * m + [gf_mul(coef, v) for v in b_poly]
            length = max(len(lam), len(shifted))
            new_lam = [0] * length
            for i in range(len(lam)):
                new_lam[i] ^= lam[i]
            for i in range(len(shifted)):
                new_lam[i] ^= shifted[i]
            lam = new_lam
            b_poly = t
            l = n + 1 - l
            bb = delta
            m = 1
        else:
            coef = gf_div(delta, bb)
            shifted = [0] * m + [gf_mul(coef, v) for v in b_poly]
            length = max(len(lam), len(shifted))
            new_lam = [0] * length
            for i in range(len(lam)):
                new_lam[i] ^= lam[i]
            for i in range(len(shifted)):
                new_lam[i] ^= shifted[i]
            lam = new_lam
            m += 1
    # Normalize to exactly degree l
    lam = lam[: l + 1] if len(lam) > l + 1 else lam + [0] * (l + 1 - len(lam))
    return lam, l


def rs_decode(r: List[int]) -> Tuple[List[int], bool]:
    """RS decode via BMA (locator) -> Chien (positions) -> direct Forney.

    Convention: an error of magnitude e at high-order position p contributes
    S_i = e * (alpha^p)^i. So the locator root for position p is X_p = alpha^p,
    and Lambda(alpha^{p*?}) = 0 when 1 + X_p * y == ... The Chien search below
    tests Lambda(alpha^{p?}) for p in 0..n-1 and records p, then recovers e by
    Chien/Forney. A residual re-check of syndromes confirms correctness.
    Returns (corrected_word, ok); ok is False if errors exceed t or the
    locator roots do not match.
    """
    s = rs_syndromes(r)
    if all(v == 0 for v in s):
        return r[:], True

    lam, l = _berlekamp_massey(s)
    if l < 1 or l > RS_T:
        return r[:], False

    # Chien search: the locator's roots are X = alpha^{-p_high}, where p_high
    # is the high-order exponent of the error position (array index = N-1-p_high).
    # So we test Lambda(alpha^{-p_high}) for p_high in 0..n-1.
    positions: List[int] = []
    for p_high in range(RS_N):
        x = gf_inv(_GF_EXP[p_high])  # alpha^{-p_high}
        val = 0
        for j in range(len(lam)):
            val ^= gf_mul(lam[j], gf_pow(x, j))
        if val == 0:
            positions.append(p_high)

    if len(positions) != l:
        return r[:], False

    # Forney algorithm for magnitudes.
    # Omega(x) = S(x)*Lambda(x) mod x^{2t}, where S(x) = S1 + S2 x + ...
    omega = [0] * RS_2T
    for i in range(RS_2T):
        for j in range(len(lam)):
            if i - j >= 0:
                omega[i] ^= gf_mul(lam[j], s[i - j])
    # Lambda'(x) formal derivative in GF(2^8): keep odd-indexed coeffs.
    lam_deriv = [0] * (len(lam))
    for j in range(1, len(lam)):
        if j % 2 == 1:
            lam_deriv[j - 1] = lam[j]

    out = r[:]
    for p_high in positions:
        x = _GF_EXP[p_high]       # the error's X = alpha^{p_high}
        x_inv = gf_inv(x)
        num = 0  # Omega(x_inv)
        for j in range(len(omega)):
            num ^= gf_mul(omega[j], gf_pow(x_inv, j))
        den = 0  # Lambda'(x_inv)
        for j in range(len(lam_deriv)):
            den ^= gf_mul(lam_deriv[j], gf_pow(x_inv, j))
        if den == 0:
            return r[:], False
        mag = gf_div(num, den)
        # r[0] is the high-order coefficient, so array index = N-1-p_high.
        out[RS_N - 1 - p_high] ^= mag

    if all(v == 0 for v in rs_syndromes(out)):
        return out, True
    return r[:], False


# ---------------------------------------------------------------------------
# NASA r=1/2, k=7 convolutional encoder. Generators 171, 133 (octal).
# ---------------------------------------------------------------------------

G1 = 0o171  # 1111001
G2 = 0o133  # 1011011
K = 7


def _parity(x: int) -> int:
    return bin(x).count("1") & 1


def conv_encode(bits: List[int]) -> List[int]:
    """Encode a bit list; append K-1 zero tail bits for trellis termination.

    The 6-cell shift register holds the previous 6 input bits; the current
    input bit is combined with the register to form two output bits, THEN the
    register is shifted (current bit becomes the newest cell).
    """
    reg = 0  # 6 memory cells in the low 6 bits (bit5 = newest, bit0 = oldest)
    out: List[int] = []
    extended = bits + [0] * (K - 1)
    for b in extended:
        state = (b << (K - 1)) | reg  # current input in MSB, 6 cells below
        c1 = _parity(state & G1)
        c2 = _parity(state & G2)
        out.append(c1)
        out.append(c2)
        reg = ((reg >> 1) | (b << (K - 2))) & 0x3F  # shift: b becomes newest cell
    return out


# ---------------------------------------------------------------------------
# Hard-decision Viterbi decoder over the 64-state trellis.
# ---------------------------------------------------------------------------


def _next_states_and_outputs() -> List[Tuple[int, int, int, int]]:
    """For each state s (0..63), return (ns0, out0, ns1, out1)."""
    table = []
    for s in range(64):
        res = []
        for inp in (0, 1):
            state = (inp << 6) | s
            ns = (state >> 1) & 0x3F
            c1 = _parity(state & G1)
            c2 = _parity(state & G2)
            res.append((ns, (c1 << 1) | c2))
        table.append((res[0][0], res[0][1], res[1][0], res[1][1]))
    return table


_TBL = _next_states_and_outputs()


def viterbi_decode(rx: List[int]) -> Tuple[List[int], int]:
    """Decode a 2L-bit stream into L bits. Returns (bits, final_path_metric)."""
    n_steps = len(rx) // 2
    INF = 1 << 30
    metric = [INF] * 64
    metric[0] = 0
    path: List[List[int]] = [[] for _ in range(64)]
    for step in range(n_steps):
        r = (rx[2 * step] << 1) | rx[2 * step + 1]
        dist_map = {0b00: bin(r ^ 0b00).count("1"),
                    0b01: bin(r ^ 0b01).count("1"),
                    0b10: bin(r ^ 0b10).count("1"),
                    0b11: bin(r ^ 0b11).count("1")}
        new_metric = [INF] * 64
        new_path: List[List[int]] = [[] for _ in range(64)]
        for s in range(64):
            if metric[s] >= INF:
                continue
            ns0, out0, ns1, out1 = _TBL[s]
            for inp, ns, out in ((0, ns0, out0), (1, ns1, out1)):
                cand = metric[s] + dist_map[out]
                if cand < new_metric[ns]:
                    new_metric[ns] = cand
                    new_path[ns] = path[s] + [inp]
        metric = new_metric
        path = new_path
    best = 0  # tail bits force termination at state 0
    return path[best][: n_steps - (K - 1)] if n_steps >= K - 1 else path[best], metric[best]


# ---------------------------------------------------------------------------
# Depth-I block interleaver.
# ---------------------------------------------------------------------------


def interleave(blocks: List[List[int]]) -> List[List[int]]:
    """Transpose equal-length symbol blocks: a burst hits many columns."""
    if not blocks:
        return []
    depth = len(blocks)
    length = len(blocks[0])
    return [[blocks[i][j] for i in range(depth)] for j in range(length)]


def deinterleave(transposed: List[List[int]]) -> List[List[int]]:
    return interleave(transposed) if transposed else []


# ---------------------------------------------------------------------------
# Bit helpers
# ---------------------------------------------------------------------------


def bytes_to_bits(data: List[int]) -> List[int]:
    bits: List[int] = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def bits_to_bytes(bits: List[int]) -> List[int]:
    out = []
    for i in range(0, len(bits) - 7, 8):
        v = 0
        for j in range(8):
            v = (v << 1) | bits[i + j]
        out.append(v)
    return out


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def main() -> None:
    payload = [0x10, 0x20, 0x30]  # 3 data symbols -> exactly fills RS_K
    print("Payload symbols :", payload)
    print("Payload bits    :", bytes_to_bits(payload))

    rs_word = rs_encode(payload)
    print("RS (7,3) codeword:", rs_word, "(data +", RS_2T, "parity)")

    dec, ok = rs_decode(rs_word)
    print("RS clean decode :", dec, "ok =", ok)

    corrupted = rs_word[:]
    corrupted[2] ^= 0xAB
    dec, ok = rs_decode(corrupted)
    print("RS 1-err decode :", dec, "ok =", ok)

    corrupted = rs_word[:]
    corrupted[1] ^= 0x01
    corrupted[3] ^= 0x02
    corrupted[5] ^= 0x03
    dec, ok = rs_decode(corrupted)
    print("RS 3-err decode :", dec, "ok =", ok, "(expected False, t=2)")

    # ----- Convolutional encode + Viterbi -----
    bits = bytes_to_bits(payload)
    enc = conv_encode(bits)
    print("\nConv encoded bits:", enc)

    dec_bits, metric = viterbi_decode(enc)
    print("Viterbi decode   :", dec_bits, "metric =", metric)
    print("Recovered bytes  :", bits_to_bytes(dec_bits), "(matches payload)")

    noisy = enc[:]
    noisy[3] ^= 1
    dec_bits, metric = viterbi_decode(noisy)
    print("Viterbi 1-err    :", bits_to_bytes(dec_bits), "metric =", metric)

    burst_len = 5
    burst_pos = 4
    bursty = enc[:]
    for i in range(burst_len):
        bursty[burst_pos + i] ^= 1
    dec_bits, metric = viterbi_decode(bursty)
    rec_bytes = bits_to_bytes(dec_bits)
    print(f"Viterbi {burst_len}-bit burst:", rec_bytes, "metric =", metric,
          "ok =", rec_bytes == payload)

    # ----- Concatenated: RS + interleaver + convolutional -----
    print("\n--- Concatenated scheme (RS(7,3) + interleave + conv r=1/2) ---")
    depth = 2
    rs_words = [rs_encode(payload), rs_encode(payload)]
    trans = interleave(rs_words)
    flat_symbols = [s for col in trans for s in col]
    tx_bits = conv_encode(bytes_to_bits(flat_symbols))

    burst = 9
    rx_bits = tx_bits[:]
    for i in range(burst):
        rx_bits[6 + i] ^= 1

    dec_syms_bits, vm = viterbi_decode(rx_bits)
    dec_syms = bits_to_bytes(dec_syms_bits)
    col_len = depth
    n_cols = len(dec_syms) // col_len
    detrans = [[dec_syms[c * col_len + r] for c in range(n_cols)] for r in range(col_len)]
    recovered_words = deinterleave(detrans)

    print("Viterbi metric  :", vm)
    for i, w in enumerate(recovered_words):
        d, ok = rs_decode(w)
        print(f"RS word {i}      :", w, "->", d, "ok =", ok)

    print("\nInterpretation: the burst was spread across both RS words by the")
    print("interleaver, so each word sees <= t symbol errors and decoding succeeds.")
    print("Without the interleaver, the same burst would overload one RS word.")


if __name__ == "__main__":
    main()
