"""
Reed-Solomon (255, 223) code over GF(2^8) — burst-error correction demo.

Implements the finite field GF(2^8) with the irreducible polynomial
0x11D (x^8 + x^4 + x^3 + x^2 + 1), systematic encoding via polynomial
long division by the generator g(x) = (x - a^1)...(x - a^32), and the
full decoding pipeline: syndromes, Berlekamp-Massey for the
error-locator polynomial, Chien search, Forney's algorithm for error
magnitudes, and correction.

Stdlib only. Run: python3 main.py
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Finite field GF(2^8) defined by p(x) = x^8 + x^4 + x^3 + x^2 + 1  (0x11D)
# ---------------------------------------------------------------------------

PRIMITIVE_POLY = 0x11D  # 1_0001_1101 in 9 bits
FIELD_SIZE = 256        # 2^8

# exp[i]   = a^i   where a = 0x02 is a primitive element
# log[x]   = i     such that a^i == x
_exp: list[int] = [0] * (FIELD_SIZE * 2)  # doubled to avoid mod in mul
_log: list[int] = [0] * FIELD_SIZE


def build_field_tables() -> None:
    """Populate the exp/log tables for GF(2^8)."""
    x = 1
    for i in range(FIELD_SIZE - 1):
        _exp[i] = x
        _log[x] = i
        # multiply x by a (= 0x02): left shift, reduce mod p(x) if overflow
        x <<= 1
        if x & 0x100:
            x ^= PRIMITIVE_POLY
    # replicate so exp[i + 255] == exp[i] (no modulo needed in gf_mul)
    for i in range(FIELD_SIZE - 1, FIELD_SIZE * 2):
        _exp[i] = _exp[i - (FIELD_SIZE - 1)]


def gf_mul(a: int, b: int) -> int:
    """Multiply two field elements via log/antilog tables."""
    if a == 0 or b == 0:
        return 0
    return _exp[(_log[a] + _log[b]) % (FIELD_SIZE - 1)]


def gf_div(a: int, b: int) -> int:
    """Divide a by b in GF(2^8). Raises on division by zero."""
    if b == 0:
        raise ZeroDivisionError("gf_div by zero")
    if a == 0:
        return 0
    return _exp[(_log[a] - _log[b]) % (FIELD_SIZE - 1)]


def gf_inv(a: int) -> int:
    """Multiplicative inverse of a nonzero element."""
    if a == 0:
        raise ZeroDivisionError("gf_inv of zero")
    return _exp[(FIELD_SIZE - 1 - _log[a]) % (FIELD_SIZE - 1)]


def gf_pow(a: int, e: int) -> int:
    """a^e in GF(2^8)."""
    if e == 0:
        return 1
    if a == 0:
        return 0
    return _exp[(_log[a] * e) % (FIELD_SIZE - 1)]


# ---------------------------------------------------------------------------
# Reed-Solomon (255, 223) parameters
# ---------------------------------------------------------------------------

N = 255          # codeword length in symbols
K = 223          # data symbols
TWO_T = N - K    # 32 parity symbols
T = TWO_T // 2   # corrects up to 16 symbol errors


def build_generator_poly(degree: int) -> list[int]:
    """
    g(x) = (x - a^1)(x - a^2) ... (x - a^degree).
    Returns coefficients high-degree-first.
    """
    g = [1]
    for i in range(1, degree + 1):
        root = _exp[i]
        # multiply g by (x - root) = (x + root) in characteristic-2 field
        new_g = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            new_g[j] ^= c                       # x term
            new_g[j + 1] ^= gf_mul(c, root)     # constant term
        g = new_g
    return g


def rs_encode(data: list[int], gen: list[int]) -> list[int]:
    """
    Systematic encoding. data has K symbols; returns N symbols
    (data followed by 2t parity). Computes x^(2t) d(x) mod g(x).
    """
    assert len(data) == K
    parity_count = len(gen) - 1
    msg = data + [0] * parity_count
    for i in range(K):
        coef = msg[i]
        if coef == 0:
            continue
        for j in range(1, len(gen)):
            msg[i + j] ^= gf_mul(gen[j], coef)
    return data + msg[K:]


def rs_syndromes(recv: list[int]) -> list[int]:
    """
    Compute 2t syndromes S_i = r(a^i) for i = 1..2t via Horner's method.
    Polynomial treated as high-degree-first: recv[0] is x^(n-1).
    """
    synd = [0] * TWO_T
    for i in range(1, TWO_T + 1):
        root = _exp[i]
        acc = 0
        for coef in recv:
            acc = gf_mul(acc, root) ^ coef
        synd[i - 1] = acc
    return synd


def berlekamp_massey(syndromes: list[int]) -> list[int]:
    """
    Berlekamp-Massey algorithm. Returns the error-locator polynomial
    Lambda(x) as coefficients low-degree-first. Raises ValueError
    if the locator degree exceeds t (uncorrectable).
    """
    lam = [1]
    b = [1]
    l = 0
    m = 1
    b_prev = 1
    for n in range(TWO_T):
        delta = syndromes[n]
        for i in range(1, l + 1):
            delta ^= gf_mul(lam[i], syndromes[n - i])
        if delta == 0:
            m += 1
        elif 2 * l <= n:
            t_copy = lam[:]
            coef = gf_div(delta, b_prev)
            if len(lam) < len(b) + m:
                lam.extend([0] * (len(b) + m - len(lam)))
            for i in range(len(b)):
                lam[i + m] ^= gf_mul(coef, b[i])
            l = n + 1 - l
            b = t_copy
            b_prev = delta
            m = 1
        else:
            coef = gf_div(delta, b_prev)
            if len(lam) < len(b) + m:
                lam.extend([0] * (len(b) + m - len(lam)))
            for i in range(len(b)):
                lam[i + m] ^= gf_mul(coef, b[i])
            m += 1
    while len(lam) > 1 and lam[-1] == 0:
        lam.pop()
    if len(lam) - 1 > T:
        raise ValueError(
            f"uncorrectable: locator degree {len(lam) - 1} > t={T}"
        )
    return lam


def chien_search(lam: list[int]) -> list[int]:
    """
    Find error positions and return them as ARRAY INDICES into the
    codeword. Array index i corresponds to the coefficient of x^(N-1-i),
    so its locator value is X = a^(N-1-i) and Lambda has root X^-1 = a^(-j)
    with j = N-1-i. We test each exponent j in 0..N-1 and convert back.
    """
    positions: list[int] = []
    for j in range(N):
        root = _exp[(255 - j) % 255] if j != 0 else 1  # a^(-j)
        acc = 0
        for k, c in enumerate(lam):
            if c == 0:
                continue
            if k == 0:
                acc ^= c
            else:
                acc ^= gf_mul(c, gf_pow(root, k))
        if acc == 0:
            array_index = (N - 1) - j
            positions.append(array_index)
    return positions


_INIT_ROOT_EXP = 1  # generator roots are a^1 .. a^(2t)


def compute_error_evaluator(syndromes: list[int], lam: list[int]) -> list[int]:
    """
    Compute the error-evaluator polynomial Omega(x) = S(x) * Lambda(x)
    mod x^(2t), low-degree-first. syndromes[i] = S_(i+1).
    """
    omega = [0] * TWO_T
    for i, c in enumerate(lam):
        if c == 0:
            continue
        for j in range(TWO_T - i):
            omega[i + j] ^= gf_mul(c, syndromes[j])
    while len(omega) > 1 and omega[-1] == 0:
        omega.pop()
    return omega


def forney_magnitudes(
    syndromes: list[int], lam: list[int], positions: list[int]
) -> list[int]:
    """
    Compute error magnitudes via Forney's algorithm:
        e_l = X_l * Omega(X_l^-1) / Lambda'(X_l^-1)
    Lambda(x) has root X_l^-1 where X_l = a^(N-1-pos). lam is
    low-degree-first.
    """
    omega = compute_error_evaluator(syndromes, lam)
    mags: list[int] = []
    for pos in positions:
        xi = _exp[(N - 1 - pos) % 255]       # X_l = a^(N-1-pos)
        xi_inv = gf_inv(xi)                  # X_l^-1
        # Lambda'(x): formal derivative in char 2 keeps odd-degree terms.
        ld_val = 0
        for j in range(1, len(lam), 2):
            if lam[j]:
                ld_val ^= gf_mul(lam[j], gf_pow(xi_inv, j - 1))
        # Omega(X_l^-1)
        o_val = 0
        for j, c in enumerate(omega):
            if c:
                o_val ^= gf_mul(c, gf_pow(xi_inv, j))
        if ld_val == 0:
            mags.append(0)
            continue
        # Forney correction factor X^(1 - b), b = first root exponent (1).
        correction = gf_pow(xi, 1 - _INIT_ROOT_EXP)   # = 1 when b == 1
        mag = gf_div(gf_mul(correction, o_val), ld_val)
        mags.append(mag)
    return mags


def rs_decode(recv: list[int]) -> tuple[list[int], bool]:
    """
    Decode a (255, 223) codeword. Returns (corrected_data, ok).
    ok is False if the pattern is uncorrectable.
    """
    synd = rs_syndromes(recv)
    if all(s == 0 for s in synd):
        return recv[:K], True
    try:
        lam = berlekamp_massey(synd)
    except ValueError:
        return recv[:K], False
    positions = chien_search(lam)
    if not positions or len(positions) != len(lam) - 1:
        return recv[:K], False
    mags = forney_magnitudes(synd, lam, positions)
    corrected = recv[:]
    for pos, mag in zip(positions, mags):
        corrected[pos] ^= mag
    if any(s != 0 for s in rs_syndromes(corrected)):
        return recv[:K], False
    return corrected[:K], True


# ---------------------------------------------------------------------------
# Demonstration: encode, inject a burst, decode, report.
# ---------------------------------------------------------------------------

def inject_burst(codeword: list[int], start: int, length: int) -> list[int]:
    """Corrupt `length` consecutive symbols starting at `start`."""
    corrupted = codeword[:]
    for i in range(length):
        pos = (start + i) % N
        corrupted[pos] ^= 0xA5  # arbitrary nonzero corruption
    return corrupted


def main() -> None:
    build_field_tables()

    print("=== GF(2^8) self-test ===")
    ok = all(gf_mul(x, gf_inv(x)) == 1 for x in range(1, FIELD_SIZE))
    print(f"  inverse round-trip (all 255 nonzero elements): {ok}")
    print(f"  gf_mul(0x57, 0x83) = 0x{gf_mul(0x57, 0x83):02X}")

    gen = build_generator_poly(TWO_T)
    print(f"\n=== RS({N},{K}) generator polynomial (degree {len(gen) - 1}) ===")
    print("  first coeffs (high-first):",
          " ".join(f"0x{c:02X}" for c in gen[:6]), "...")

    data = [(i * 7 + 3) & 0xFF for i in range(K)]
    codeword = rs_encode(data, gen)
    assert len(codeword) == N
    print(f"\n=== Encoded codeword: {K} data + {TWO_T} parity = {N} symbols ===")
    print("  parity symbols:",
          " ".join(f"0x{c:02X}" for c in codeword[K:K + 8]), "...")

    synd_clean = rs_syndromes(codeword)
    print(f"  syndromes of clean codeword all zero: "
          f"{all(s == 0 for s in synd_clean)}")

    print(f"\n=== Burst-error correction (t={T} symbols = {T * 8} bits) ===")
    for burst_len in (1, 8, 16, 17, 32):
        corrupted = inject_burst(codeword, start=100, length=burst_len)
        recovered, ok = rs_decode(corrupted)
        match = recovered == data
        bit_len = burst_len * 8
        status = "RECOVERED" if (ok and match) else "FAILED"
        print(f"  burst={burst_len:2d} syms ({bit_len:3d} bits): {status}")

    print("\n=== Budget summary ===")
    print(f"  unknown-error budget: t  = {T} symbols ({T * 8} bits)")
    print(f"  erasure budget:      2t = {TWO_T} symbols "
          f"({TWO_T * 8} bits, locations known)")
    print("\nDone. The t=16 boundary recovers; t=17 fails (the cliff).")


if __name__ == "__main__":
    main()
