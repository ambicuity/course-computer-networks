# CRC Polynomial Arithmetic and Generator Standards

> Cyclic Redundancy Check (CRC) is the dominant error-detection mechanism at the data-link layer, used in Ethernet (IEEE 802.3), 802.11 Wi-Fi, HDLC, USB, ZIP, PNG, and dozens of other standards. A CRC treats a frame's bit string as the coefficient list of a polynomial over GF(2) — the two-element field where addition and subtraction are both XOR, with no carry or borrow. The sender and receiver agree on a generator polynomial G(x); the sender appends exactly r = deg(G) check bits called the Frame Check Sequence (FCS) so that the combined polynomial T(x) is divisible by G(x). The receiver re-divides the received frame by G(x): a non-zero remainder is proof of at least one corrupted bit. A degree-r generator guarantees detection of all single-bit errors, all double-bit errors (with appropriate G(x)), all odd-parity errors if (x+1) is a factor of G(x), and — crucially — all burst errors of length ≤ r. International standards converged on CRC-32 (IEEE 802.3, HD=4) and CRC-32C / Castagnoli (RFC 3720 for iSCSI, HD=6) after Koopman's 2002 exhaustive computational search showed CRC-32C has strictly better Hamming distance for typical frame sizes.

**Type:** Build
**Languages:** Python
**Prerequisites:** Binary arithmetic, XOR, basic polynomial notation, Lesson 26 (parity and checksum)
**Time:** ~75 minutes

## Learning Objectives

- Translate a bit string into a GF(2) polynomial and perform modulo-2 long division by hand on a 10-bit example.
- State the four guaranteed error-detection properties of a degree-r CRC generator and explain the algebraic reason each holds.
- Identify the generator polynomials for CRC-16-CCITT (ITU-T V.41, HDLC), CRC-32-IEEE (IEEE 802.3), and CRC-32C (RFC 3720) and explain why CRC-32C replaced CRC-32 in storage protocols.
- Implement `compute_crc` and `verify_crc` using modulo-2 XOR long division in pure Python and reproduce the Tanenbaum Figure 3-9 worked example exactly.
- Explain the Hamming distance trade-off: CRC-32-IEEE HD=4 vs CRC-32C HD=6, and why IEEE 802.3 kept the weaker polynomial for backwards compatibility.
- Predict whether a given burst-error length will be detected or slip through undetected, using the burst-detection theorem.

## The Problem

You are integrating a new embedded NIC driver. During lab testing, the driver occasionally delivers frames that differ by one or two bits from the transmitted data — silent memory-copy bugs introduced by a DMA controller. Your test harness catches some corruptions but misses others. The engineers argue: "Just use a simple checksum — XOR all bytes." But XOR-byte checksums miss systematic bit patterns: flip bit 3 in byte 0 and bit 3 in byte 7 and the XOR checksum is unchanged. You need a guarantee: any single-bit error caught, any burst up to 32 bits caught, with only 4 bytes of overhead per frame. That is exactly what CRC-32 provides, and it is why every Ethernet frame ends with a 4-byte FCS computed over CRC-32.

The underlying machinery — polynomial division over GF(2) — looks exotic but reduces to shift-register XOR operations that fit in hardware in a few dozen gates. Understanding the algebra lets you choose the right generator for the right job, reason about what classes of errors escape detection, and implement or debug the check in software.

## The Concept

### GF(2) Polynomial Representation

A k-bit frame is treated as the coefficients of a polynomial of degree k−1 over GF(2), the field with elements {0, 1}. The leftmost (most-significant) bit is the coefficient of x^(k−1); the rightmost bit is the coefficient of x^0.

Example: the 6-bit string `110001` represents:
```
1·x⁵ + 1·x⁴ + 0·x³ + 0·x² + 0·x¹ + 1·x⁰  =  x⁵ + x⁴ + 1
```

Arithmetic in GF(2) uses modulo-2 rules:
- Addition and subtraction are identical: both are XOR.
- No carry, no borrow.
- 1+1 = 0,  0+0 = 0,  1+0 = 1.

This means polynomial multiplication and division proceed exactly like standard long division, except each coefficient operation is an XOR rather than a numeric add/subtract. The textbook worked example (Tanenbaum §3.2.2, Figure 3-9) uses frame `1101011111` and generator G(x) = x⁴+x+1 (bit pattern `10011`). See `assets/27-crc-polynomial-math-and-generator-standards.svg` for the full step-by-step visualization.

### The CRC Algorithm

Given a frame of m bits (polynomial M(x)) and a generator G(x) of degree r:

**Step 1 — Pad:** Append r zero bits to the frame. This corresponds to computing x^r · M(x). The padded frame is m+r bits long.

**Step 2 — Divide:** Perform modulo-2 long division of x^r·M(x) by G(x). Record the remainder R(x), which is at most r bits (degree ≤ r−1).

**Step 3 — Subtract remainder:** Replace the r appended zeros with R(x) by XOR-ing them in. Because we are in GF(2), subtraction and addition are the same operation, so the result T(x) = x^r·M(x) − R(x) = x^r·M(x) XOR R(x).

The resulting T(x) is exactly divisible by G(x) — that is the invariant the receiver checks.

**Receiver check:** Divide the received frame by G(x). If the remainder is zero, no error was detected. If the remainder is non-zero, at least one bit was flipped.

Worked example from Tanenbaum Figure 3-9:
```
Frame M(x)    :  1101011111  (10 bits)
Generator G(x):  10011       (x⁴+x+1, r=4)
Padded frame  :  11010111110000  (append 4 zeros)
After division:  remainder = 0010
Transmitted   :  1101011111 0010  (14 bits total)
```

`code/main.py` contains `compute_crc()` and `verify_crc()` that reproduce this exactly.

### Modulo-2 Long Division Step by Step

```
11010111110000   ← padded frame (dividend)
10011            ← generator (divisor), aligned to first 1 bit
─────────────
 1001            ← XOR result (prefix of remaining dividend)
  10011          ← align divisor to next leading 1
  ─────
  00001
  ...
─────────────
          0010   ← final remainder R(x): this becomes the CRC/FCS
```

A divisor "goes into" the dividend whenever the current leftmost dividend bit is 1. XOR the divisor into those bit positions, producing a partial remainder. Continue until fewer bits remain than the divisor length. The leftmost bit of the divisor is always 1 (this is a requirement on G(x): both the leading and trailing coefficients must be 1), which guarantees the leading 1 of the dividend is always cancelled.

### Error Detection Properties

Let E(x) represent the error pattern introduced during transmission — each '1' bit in E(x) corresponds to a flipped bit. The receiver computes [T(x)+E(x)] / G(x). Since T(x) is divisible by G(x), the result is E(x)/G(x). The error is detected if and only if G(x) does not divide E(x).

**Property 1 — All single-bit errors.** A single-bit flip means E(x) = x^i for some i. Since x^i has only one term, it is not divisible by any polynomial with two or more terms. All standard generators have at least two terms (the x^r and x^0 terms are required to be 1), so single-bit errors are always detected.

**Property 2 — All double-bit errors.** E(x) = x^i + x^j = x^j(x^(i−j)+1). A generator G(x) that is primitive and does not divide x^k+1 for any k up to the maximum frame length will catch all double errors. The choice of generator polynomial matters here: x¹⁵+x¹⁴+1 will not divide x^k+1 for any k < 32,768.

**Property 3 — All odd-parity errors.** No polynomial with an odd number of terms has (x+1) as a factor in GF(2). If G(x) includes (x+1) as a factor — which CRC-32-IEEE and CRC-32C both do — then all odd-bit-count error patterns are caught. This covers the case of three, five, or any odd number of random bit flips.

**Property 4 — All burst errors of length ≤ r.** This is the most operationally important guarantee. A burst error of length k is represented as x^i(x^(k−1)+…+1). If k < r, the degree of the bracketed expression is less than deg(G(x)), so G(x) cannot divide it. This means a 32-bit CRC catches every burst error of 32 bits or fewer — unconditionally, not probabilistically. For burst length r+1, the error is missed only if the burst pattern exactly matches G(x), which has probability 2^(−(r−1)) for random errors. For longer bursts, the probability of slipping through is 2^(−r).

| Error type | Condition on G(x) | Detection guarantee |
|---|---|---|
| All single-bit | G(x) has ≥ 2 terms | 100% |
| All double-bit | G(x) is primitive, not dividing x^k+1 | 100% up to max frame len |
| All odd-parity | (x+1) \| G(x) | 100% |
| Burst ≤ r bits | Always | 100% |
| Burst = r+1 bits | — | Misses with prob 2^(−(r−1)) |
| Burst > r+1 bits | — | Misses with prob 2^(−r) |

### Standard Generator Polynomials

**CRC-16-IBM (x¹⁶+x¹⁵+x²+1):** Used in IBM's BISYNC protocol and USB bulk/interrupt transfers. The 17-bit pattern is `0x18005`. Provides HD=4 for messages up to 32,767 bytes.

**CRC-16-CCITT (x¹⁶+x¹²+x⁵+1):** Standardized in ITU-T V.41. Used in HDLC framing (the basis for PPP, ISDN, X.25), Bluetooth, and many embedded protocols. Polynomial `0x11021`. Provides HD=4. Also called CRC-CCITT or CRC-16/CCITT-FALSE depending on initialization vector.

**CRC-32-IEEE (x³²+x²⁶+x²³+x²²+x¹⁶+x¹²+x¹¹+x¹⁰+x⁸+x⁷+x⁵+x⁴+x²+x+1):** The dominant 32-bit CRC since the 1980s. Adopted by IEEE 802.3 (Ethernet), 802.11 (Wi-Fi), PKzip, gzip, PNG, and virtually all LAN and point-to-point standards. Polynomial `0x04C11DB7` (normal form) or `0xEDB88320` (reflected form used in table-driven software implementations). Detects all bursts ≤ 32 bits, provides HD=4 for frames up to 11,454 bytes.

**CRC-32C / Castagnoli (x³²+x²⁸+x²⁷+x²⁶+x²⁵+x²³+x²²+x²⁰+x¹⁹+x¹⁸+x¹⁴+x¹³+x¹¹+x¹⁰+x⁹+x⁸+x⁶+1):** Found by Castagnoli et al. (1993) and popularized by Koopman (2002). Polynomial `0x1EDC6F41`. Provides HD=6 for frames up to 32,767 bytes — compared to HD=4 for CRC-32-IEEE. Standardized in RFC 3720 (iSCSI) and RFC 4960 (SCTP). Also used by Linux Btrfs and ext4 for metadata checksums, Intel's hardware CRC32 instruction (SSE4.2 `crc32` opcode), and Brotli compression.

### Hamming Distance and Why It Matters

Hamming distance (HD) of an error-detecting code is the minimum number of bit flips needed to transform one valid codeword into another without the code detecting the change. A code with HD=d detects all error patterns of weight up to d−1.

- CRC-32-IEEE: HD=4 for frames ≤ 11,454 bytes. Detects all 1, 2, 3-bit errors. A 4-bit error pattern could theoretically slip through if it aligns with a multiple of G(x).
- CRC-32C: HD=6 for frames ≤ 32,767 bytes. Detects all 1–5 bit errors. Substantially stronger for storage systems where silent data corruption is the dominant failure mode.

Koopman and Chakravarty (2004, IEEE DSN) showed that for any given frame size and CRC width, some generators achieve strictly higher HD than others. CRC-32-IEEE has been retained in Ethernet purely for hardware backwards compatibility — all existing NICs implement it in silicon. New protocols (iSCSI, SCTP, storage checksums) adopted CRC-32C because there is no legacy constraint.

### Hardware vs Software Implementation

In hardware, CRC is computed by a linear feedback shift register (LFSR). The register is r bits wide; taps correspond to the non-zero terms of G(x). Each incoming bit triggers one shift-and-XOR cycle. A 32-bit CRC of an entire Ethernet frame (up to 1500-byte payload) completes in wire-speed hardware with essentially zero latency.

In software, the naive bit-by-bit algorithm runs in O(n·r) time. The standard optimization is a lookup table of 256 pre-computed 32-bit remainders (one per byte value), reducing the computation to O(n) with 1 KB of table. Modern x86 processors with SSE4.2 include a hardware `crc32` instruction that computes CRC-32C over 8 bytes per clock cycle (~20 GB/s on a 3 GHz core).

`code/main.py` implements the pure-Python bit-by-bit algorithm to make the GF(2) arithmetic visible. The `xor_divide()` function is the core — it performs modulo-2 long division one bit at a time using Python list operations.

## Build It

1. Run `python3 code/main.py` and verify that Section 1 output matches Tanenbaum Figure 3-9 exactly: remainder `0010`, transmitted frame `11010111110010`.

2. Open `code/main.py` and read `xor_divide()`. Trace through the first four iterations manually against the division steps in `assets/27-crc-polynomial-math-and-generator-standards.svg`. Confirm the XOR at each step.

3. In `compute_crc()`, note that Step 3 is implicit: the padded zeros in `padded = frame_bits + [0] * degree` are replaced by the remainder via list replacement, not a second XOR pass. Explain to yourself why `frame_bits + remainder` equals the XOR of the padded frame with the remainder.

4. Add a call to `compute_crc` with your own 8-bit payload and the `CRC-16-CCITT` generator. Print the FCS in hex. Then manually verify by re-dividing the transmitted frame using the `xor_divide` function directly and confirming the remainder is all-zero.

5. Extend `inject_burst_error` to inject an error starting exactly at the FCS field (last 16 bits for CRC-16, last 32 bits for CRC-32). Observe that the receiver still detects it — the FCS itself is protected because the entire transmitted frame (data + FCS) is divided by G(x).

6. Test the r+1 burst boundary: inject a burst of exactly r+1=5 bits for the CRC-4 textbook generator. Run 1000 random frame trials and measure what fraction are detected. The theoretical expectation is 1 − 2^(−(r−1)) = 1 − 0.25 = 75% detected.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Reproduce textbook example | `python3 code/main.py` Section 1 | Remainder `0010`, T(x) = `11010111110010`, receiver returns PASS for clean and DETECTED for flipped frame |
| Verify burst ≤ r always caught | Section 3 output for CRC-32 burst-16 and burst-32 rows | Both show `ERROR DETECTED`, never `PASS` |
| Understand Hamming distance trade-off | Section 4 output | CRC-32-IEEE HD=4, CRC-32C HD=6, correct frame size bounds |
| Identify protocol-to-generator mapping | Section 2 table | HDLC → CRC-16-CCITT; Ethernet → CRC-32-IEEE; iSCSI → CRC-32C |
| Trace xor_divide manually | Step-by-step trace on paper | First XOR step: `11010 XOR 10011 = 01001`, remainder propagates correctly |

## Ship It

Running `python3 code/main.py` produces console output demonstrating all four sections. Copy the full terminal output into `outputs/` as evidence of a working CRC implementation. The SVG at `assets/27-crc-polynomial-math-and-generator-standards.svg` serves as a reference diagram for the polynomial representation, pipeline steps, XOR arithmetic rules, and standards comparison table.

## Exercises

1. **Manual division:** Divide the bit string `10011101` (M(x)) by generator polynomial x³+1 (bit pattern `1001`) using modulo-2 long division on paper. Show each XOR step. What are the 3 check bits appended? What is the transmitted frame? (This is Tanenbaum Problem 17.)

2. **Generator requirements:** The specification for G(x) states both the leading and trailing bits must be 1. Construct a counterexample: choose a generator with a trailing `0` (e.g., `10010`) and show a class of single-bit errors it will miss, using the algebraic argument from the Property 1 section.

3. **Burst boundary experiment:** Modify `code/main.py` to test 10,000 random 32-bit frames with the CRC-4-textbook generator. Inject burst errors of length 5 (= r+1). Count how many pass the `verify_crc` check. Compare to the theoretical bound of 2^(−(r−1)) = 25% undetected. How close is your empirical result?

4. **Protocol identification:** A network trace shows frames ending in a 2-byte FCS. The frames carry serial data with HDLC-style flag bytes `0x7E`. Which generator polynomial is in use? What is its Hamming distance for the frame sizes you observe? If you wanted stronger detection without changing the FCS field width, what alternative generator would you pick?

5. **CRC-32C vs CRC-32-IEEE:** A storage engineer argues: "CRC-32 is fine — it's been in Ethernet for 40 years." Construct a precise counter-argument using Hamming distance, message size range, and a specific scenario where HD=4 is insufficient (e.g., a 4-bit memory corruption pattern in a 4 KB block). Cite Koopman (2002).

6. **Odd error detection:** G(x) = x³+1 = (x+1)(x²+x+1) in GF(2). Confirm that (x+1) is a factor of x³+1 by polynomial multiplication. Then construct a 3-bit error pattern E(x) with an odd number of terms and verify algebraically that G(x) does not divide E(x), proving the odd-error property holds.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| CRC | "the checksum at the end of the frame" | A polynomial remainder computed over GF(2); not a simple checksum — provides algebraic burst-error guarantees |
| FCS | "frame check sequence" | The r-bit CRC field appended to a frame; in Ethernet it is 4 bytes using CRC-32-IEEE |
| Generator polynomial G(x) | "the CRC polynomial" | The agreed divisor; both leading and trailing bits must be 1; its degree r determines how many check bits are appended |
| Modulo-2 arithmetic | "XOR division" | Polynomial arithmetic over GF(2): + and − are both XOR, no carry or borrow; standard long division applies with XOR replacing subtraction |
| GF(2) | "binary field" | The Galois field with two elements {0,1}; the algebraic structure that makes CRC analysis tractable |
| Burst error | "a run of bad bits" | An error pattern starting and ending with a '1', with arbitrary bits in between; CRC-r catches all bursts ≤ r bits long |
| Hamming distance (HD) | "how strong the code is" | Minimum number of bit flips to turn one valid codeword into another; HD=d means all (d-1)-bit errors are caught |
| CRC-32-IEEE | "Ethernet CRC" | The IEEE 802.3 standard generator (0x04C11DB7); HD=4 for ≤11,454-byte frames; in Ethernet NICs, USB, ZIP, 802.11 |
| CRC-32C | "Castagnoli CRC" | Generator 0x1EDC6F41; HD=6 for ≤32,767-byte frames; used in iSCSI (RFC 3720), SCTP (RFC 4960), Btrfs, Intel `crc32` instruction |
| LFSR | "shift register CRC" | Linear Feedback Shift Register; hardware circuit that computes CRC at wire speed by tapping bits corresponding to G(x) terms |
| Remainder R(x) | "the CRC bits" | The result of dividing x^r·M(x) by G(x); appended to the frame so T(x) = x^r·M(x) − R(x) is divisible by G(x) |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §3.2.2 "Polynomial Codes" — the primary source for the Figure 3-9 worked example and error-detection proofs used in this lesson.
- **IEEE 802.3-2018**, Clause 3.2.9 — normative specification of the CRC-32 FCS field in Ethernet frames; includes the generator polynomial and initialization/finalization constants.
- **RFC 3720** (iSCSI, 2004), Section 12.1 — mandates CRC-32C for the iSCSI data digest and header digest fields; explains rationale over CRC-32-IEEE.
- **RFC 4960** (SCTP, 2007), Section 6.8 — specifies CRC-32C as the SCTP checksum, replacing the earlier Adler-32 (RFC 2960).
- Castagnoli, G., Bräuer, S., & Herrmann, M. (1993). "Optimization of Cyclic Redundancy-Check Codes with 24 and 32 Parity Bits." *IEEE Transactions on Communications*, 41(6), 883–892. — original paper identifying CRC-32C.
- Koopman, P. & Chakravarty, T. (2004). "Cyclic Redundancy Code (CRC) Polynomial Selection for Embedded Networks." *International Conference on Dependable Systems and Networks (DSN)*. — exhaustive computational search comparing HD across generators and frame sizes; the definitive reference for CRC polynomial selection.
- Peterson, W.W. & Brown, D.T. (1961). "Cyclic Codes for Error Detection." *Proceedings of the IRE*, 49(1). — foundational paper on LFSR hardware implementation of CRC.
- Williams, R. (1993). "A Painless Guide to CRC Error Detection Algorithms." — widely cited technical reference covering initialization, reflection, and finalization constants that explain why software CRC-32 uses 0xFFFFFFFF init and `0xEDB88320` (reflected polynomial).
