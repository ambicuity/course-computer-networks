# Building CRC Polynomial Division and Checksums

> A data link can move a frame a thousand kilometers, but it cannot make the channel honest — bits still flip from thermal noise, crosstalk, and faulty line drivers. Three families of error-detecting codes answer this at the link layer. **Parity** adds one XOR bit per block and catches any single-bit error but only half of long bursts. **Checksums** (the 16-bit Internet checksum of RFC 1071, used in the IPv4 header, TCP, UDP, and ICMP) sum 16-bit words in one's-complement arithmetic and fold the carry back end-around, but they are position-blind: they miss byte insertions, deletions, and reordering. **Cyclic Redundancy Checks (CRCs)** treat the frame as a polynomial over GF(2), append r zero bits, divide by an agreed generator G(x), and transmit the remainder in place of the zeros so the received codeword is exactly divisible by G(x) — a degree-r CRC catches all single-bit errors, all double errors (up to a frame-length bound), all odd-count errors (if x+1 divides G(x)), and every burst of length ≤ r, which is why Ethernet's FCS, 802.11, HDLC, and PPP all run CRC-32 with the IEEE 802 polynomial `0x04C11DB7`. The failure mode engineers hit is not "the CRC is wrong" — it is "the frame passed the CRC but the upper layer is still corrupt," which happens because CRC is detection, not correction, and a burst longer than r+1 slips through with probability 2⁻ʳ. This lesson builds a runnable polynomial divider, an RFC 1071 Internet-checksum generator, and a Fletcher-16 implementation so you can watch exactly which errors each catches and which it misses.

**Type:** Build
**Languages:** Python
**Prerequisites:** Binary arithmetic, the data-link layer framing model from the prior lessons, basic modular arithmetic
**Time:** ~75 minutes

## Learning Objectives

- Encode a frame with a CRC by appending r zero bits, performing polynomial long division over GF(2), and replacing the zeros with the remainder — and verify that the received codeword divides evenly by the generator.
- Predict which error patterns a given degree-r CRC will always catch (single-bit, double, odd-count, bursts ≤ r) and which slip through with probability 2⁻ʳ.
- Compute the 16-bit Internet checksum (RFC 1071) using one's-complement end-around-carry addition, and explain why a "good" frame sums to 0xFFFF.
- Distinguish the Internet checksum from Fletcher's checksum, and prove with a worked example why Fletcher catches byte reordering that the Internet checksum misses.
- Map each generator polynomial (CRC-4 textbook, CRC-16-CCITT, CRC-32/IEEE) to the real protocol that uses it, and read a frame's FCS field correctly.
- Diagnose the case where a frame passes its CRC yet the network layer still delivers garbage, naming the residual error probability.

## The Problem

A satellite uplink runs a 2 Mbps link over a long coax run with a measured bit error rate around 10⁻⁶. Frames are 1000 bits long, so on average one frame in a thousand arrives damaged. The link-layer designer cannot afford to retransmit every frame, and cannot afford to let a corrupted IP packet travel onward — a flipped bit in the IPv4 destination address routes the packet to the wrong network silently. The engineer needs a check value small enough to fit in a 4-byte trailer (the Ethernet FCS) that catches essentially every realistic error a noisy channel produces, plus a faster scheme for the IP/TCP/UDP headers where software computation, not hardware, is the bottleneck.

The two answers in production today are CRC (in every LAN and PPP frame) and the Internet checksum (in every IP, TCP, UDP, and ICMP packet). They are not interchangeable: CRC is strong but bit-oriented and hardware-fast; the Internet checksum is weak but byte-oriented and software-fast. This lesson builds both and shows exactly where each one breaks.

## The Concept

### Bit strings as polynomials over GF(2)

A k-bit frame is read as the coefficient list of a polynomial with k terms, from x^(k-1) down to x⁰. The string `110001` is the polynomial 1·x⁵ + 1·x⁴ + 0·x³ + 0·x² + 0·x¹ + 1·x⁰ — six terms, degree five. Polynomial arithmetic is done modulo 2: addition and subtraction are identical and both equal XOR, with no carries and no borrows. Long division proceeds exactly as in grade-school binary division, except every subtraction is an XOR. A divisor "goes into" a dividend when the dividend has at least as many bits as the divisor. See the worked division in `assets/crc-and-checksums.svg`.

### The three-step CRC algorithm

Sender and receiver agree in advance on a generator polynomial G(x) whose high- and low-order bits are both 1. Let r be the degree of G(x). To CRC a frame M(x) of m bits (m > r):

1. Append r zero bits to the low-order end of M(x), forming xʳ·M(x) — an (m+r)-bit string.
2. Divide xʳ·M(x) by G(x) using modulo-2 long division. The quotient is discarded; the remainder R(x) has at most r bits.
3. Subtract R(x) from xʳ·M(x) (modulo 2, so this is XOR). The result is the transmitted codeword T(x) = xʳ·M(x) − R(x), which is by construction divisible by G(x).

The receiver divides the incoming T(x) by the same G(x). A zero remainder means "accept"; a non-zero remainder means "an error pattern E(x) survives that G(x) does not divide." Because T(x) is a multiple of G(x), what the receiver actually computes is E(x) mod G(x). Every detectable error is one whose polynomial is *not* a multiple of G(x).

### A worked example

Frame `1101011111` (10 bits) with the textbook generator G(x) = x⁴ + x + 1, binary `10011`, degree r = 4. Append four zeros → `11010111110000`. Divide by `10011` using XOR subtraction. The remainder is `0010`. Replace the appended zeros with the remainder: the transmitted codeword is `11010111110010`. The receiver divides `11010111110010` by `10011`, gets remainder zero, and accepts. Flip any single bit — say bit 1 → `11010111110011` — and the remainder becomes non-zero: detected. `code/main.py` reproduces this division exactly and prints the codeword, the remainder, and the detection result for a single-bit corruption.

### What each error class does to the CRC

A transmission error is modeled as an error polynomial E(x) added (XORed) to T(x). Each set bit in E(x) marks a flipped bit. The receiver computes E(x) mod G(x); errors that make E(x) a multiple of G(x) slip through undetected.

| Error pattern | E(x) shape | Detected? |
|---|---|---|
| Single-bit error at position i | xⁱ | Always — if G(x) has ≥ 2 terms, it cannot divide xⁱ |
| Two isolated bit errors at i, j (i > j) | xʲ(xⁱ⁻ʲ + 1) | Always — if G(x) is not divisible by x and does not divide xᵏ+1 for any k up to the max frame length |
| Odd number of bit errors | odd number of terms | Always — if (x+1) is a factor of G(x), since no polynomial with an odd number of terms has (x+1) as a factor |
| Burst of length ≤ r | xⁱ·(degree < r polynomial) | Always — G(x) has an x⁰ term so it cannot contribute the xⁱ factor, and the parenthesized part has lower degree than G(x) so the remainder is non-zero |
| Burst of length exactly r+1 | matches G(x) shape | Misses with probability 2⁻⁽ʳ⁻¹⁾ — only if the r−1 interior bits of the burst exactly equal G(x)'s interior |
| Longer burst or multiple bursts | arbitrary | Misses with probability ≈ 2⁻ʳ |

This is the central result. A degree-32 CRC like Ethernet's makes the residual undetected-error probability for a long burst ≈ 2⁻³² ≈ 2.3 × 10⁻¹⁰, vanishingly small on a link that already drops frames at 10⁻⁶.

### Standard generator polynomials and where they live

The generator is chosen for its algebraic properties (irreducibility, the (x+1) factor, large Hamming distance for the target frame size). Several are standardized and embedded in real frame trailers.

| Polynomial | Hex (with implicit high bit) | Degree | Used by |
|---|---|---|---|
| x⁴ + x + 1 | 0x13 | 4 | Textbook example (Fig. 3-9) |
| x⁸ + x² + x + 1 | 0x107 | 8 | CRC-8 ATM HEC, SMBus |
| x¹⁶ + x¹² + x⁵ + 1 | 0x11021 | 16 | CRC-16-CCITT — HDLC, X.25, Bluetooth, PPP 2-byte FCS |
| x¹⁶ + x¹⁵ + x² + 1 | 0x18005 | 16 | CRC-16-IBM — Modbus, ARCnet |
| x³² + x²⁶ + x²³ + x²² + x¹⁶ + x¹² + x¹¹ + x¹⁰ + x⁸ + x⁷ + x⁵ + x⁴ + x² + x¹ + 1 | 0x04C11DB7 | 32 | IEEE 802 — Ethernet FCS, 802.11, FDDI, PPP 4-byte FCS |

The IEEE 802 CRC-32 (defined above) detects all bursts of length ≤ 32 and all bursts affecting an odd number of bits. Castagnoli et al. (1993) and Koopman (2002) later found better CRC-32 polynomials that achieve Hamming distance 6 for typical message sizes, versus the IEEE polynomial's distance 4 — which is why SCTP, iSCSI, and PCIe prefer CRC-32C (Castagnoli, `0x1EDC6F41`). The link layer still uses the IEEE polynomial for historical and hardware reasons.

### The Internet checksum (RFC 1071)

The 16-bit Internet checksum covers the IPv4 header (and the TCP/UDP pseudo-header plus payload for those protocols). The algorithm: treat the bytes as a sequence of 16-bit big-endian words, sum them in one's-complement arithmetic, and store the bitwise complement of the sum in the checksum field. One's-complement addition is ordinary integer addition with the high-order carry folded back into the low 16 bits — the "end-around carry." A correct packet sums to 0xFFFF, whose one's-complement is 0, which is the receiver's "no error" signal.

The trick that makes this work on a two's-complement machine is the fold: `total = (total & 0xFFFF) + (total >> 16)`, repeated once more to absorb a residual carry. `code/main.py` implements this and verifies a mock 20-byte IPv4 header. The Internet checksum is cheap to compute in software (one add per word, plus a fold) but weak: it cannot detect deletion or insertion of zero bytes, cannot detect reordering of 16-bit words, and is vulnerable to splices that join two packets — exactly the failures Partridge et al. (1995) showed are far more common on real traffic than the random-bit model predicted.

### Fletcher's checksum: adding position

Fletcher (1982) keeps two running sums modulo 255: sum1 accumulates each byte, and sum2 accumulates each value of sum1. Because sum2 is weighted by position, a reordering that leaves the plain sum unchanged still changes sum2. On the bytes `[1,2,3,4]` versus `[4,3,2,1]` the Internet checksum is identical; Fletcher-16 differs. `code/main.py` prints both to make the contrast concrete. Fletcher is stronger than the Internet checksum at the same cost but is still weaker than a CRC, which is why the link layer standardized on CRC rather than any checksum.

### CRC is detection, not correction

A frame that fails its CRC is dropped; recovery is the job of an upper-layer retransmission scheme (ARQ) or an error-correcting code on a noisier link. A frame that *passes* its CRC is almost certainly intact — but "almost" is bounded by 2⁻ʳ for the residual cases. The engineer's discipline is to match r to the channel: CRC-32 for high-quality fiber and copper where the BER is 10⁻¹⁰ and a residual of 2⁻³² is negligible; stronger forward error correction on a wireless link where the raw BER is high enough that pure detection plus retransmission would starve throughput.

## Build It

1. Read `code/main.py`. `poly_divmod` is the heart — polynomial long division over GF(2) implemented with XOR and bit-shifts. `crc_encode` appends r zero bits, divides, and substitutes the remainder.
2. Run it: `python3 code/main.py`. Confirm the textbook example prints codeword `11010111110010` with remainder `0010`, exactly matching the chapter's Figure 3-9.
3. Read the CRC-32 block: the same code, just with `G_CRC32_IEEE = 0x104C11DB7` and a 48-byte payload. Confirm the 1-bit corruption is detected.
4. Inspect `internet_checksum` on the mock IPv4 header. Confirm the computed checksum, when re-inserted into bytes 10–11, makes `verify_internet_checksum` return True.
5. Run the Fletcher-16 vs Internet reordering block. Confirm Fletcher changes on reorder while the Internet checksum does not.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Encode a frame with CRC | Appended r zeros, remainder computed, codeword = data ‖ remainder | Receiver divides codeword by G(x) and gets remainder 0 |
| Detect a single-bit error | Non-zero remainder after dividing corrupted codeword by G(x) | Detection is unconditional when G(x) has ≥ 2 terms |
| Detect a burst of length ≤ r | Non-zero remainder | Guaranteed by theory — no probability involved |
| Compute the IPv4 header checksum | 16-bit one's-complement sum with end-around carry, complement stored in the field | Re-summing all words including the checksum yields 0xFFFF |
| Catch reordering | Fletcher sum2 changes; Internet checksum does not | Choose Fletcher when position matters, CRC when strength matters |
| Size r for a channel | Residual miss probability ≈ 2⁻ʳ below the link's tolerable undetected-error rate | r=32 gives ~2.3×10⁻¹⁰, adequate for fiber BER 10⁻¹⁰ |

## Ship It

Produce one artifact under `outputs/`:

- An annotated transcript of `code/main.py`'s output, with each detection/miss explained by the algebraic rule that governs it (single-bit always caught; burst ≤ r always caught; burst r+1 slips with probability 2⁻⁽ʳ⁻¹⁾).
- A one-page reference card listing the five standard generators (CRC-4, CRC-8, CRC-16-CCITT, CRC-16-IBM, CRC-32/IEEE) with their hex, degree, and the protocol that ships them.
- A worked Internet-checksum example: an IPv4 header in hex, the 16-bit word sum, the carry folds, and the final complement — plus a corrupted header that passes the sum (a reordered pair of words) to demonstrate the weakness.

Start from the printed output of `code/main.py` and annotate each line with the rule it demonstrates.

## Exercises

1. Encode the 8-bit frame `10110011` with the generator G(x) = x³ + x + 1 (binary `1011`). Show the appended zeros, the long-division steps, the remainder, and the transmitted codeword. Then flip bit 4 and show the receiver's non-zero remainder.
2. The IEEE 802 CRC-32 polynomial has degree 32. A burst error of length exactly 33 arrives. Compute the probability it slips through undetected, and state the one shape of 33-bit burst that is always missed.
3. You are given a 20-byte IPv4 header in hex: `4500001468b1400040060000c0a80101c0a80102`. Compute the Internet checksum (RFC 1071) by hand: list the 16-bit words, their one's-complement sum with the carry folded back, and the final complement. Insert it into bytes 10–11 and verify the receiver sums to 0xFFFF.
4. Construct two different 8-byte messages that have the *same* Internet checksum but are not identical. Explain which weakness of the sum you exploited (hint: reorder two 16-bit words, or insert/remove a `0x0000` word).
5. Compare CRC-32/IEEE (Hamming distance 4 at typical message sizes) with CRC-32C Castagnoli (Hamming distance 6). For a 1500-byte Ethernet frame, how many bit errors can each *guarantee* to detect? Why does iSCSI prefer CRC-32C while Ethernet keeps CRC-32/IEEE?
6. A noisy wireless link has a raw BER of 10⁻³. Frame size is 12000 bits. Compute the expected number of corrupted frames per million, and argue whether CRC-32 detection plus ARQ retransmission is viable, or whether forward error correction should be added at the physical layer. Quantify the residual undetected-error rate the CRC leaves behind.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Generator polynomial G(x) | "the CRC polynomial" | An agreed polynomial over GF(2) with both end bits = 1; the codeword is built to be divisible by it, and the receiver checks divisibility |
| Codeword T(x) | "the sent frame" | The data with r zero bits appended and then the remainder XORed in, so T(x) is a multiple of G(x) |
| Remainder R(x) | "the CRC" | The r-bit result of dividing xʳ·M(x) by G(x); transmitted in place of the appended zeros |
| FCS | "the trailer" | Frame Check Sequence — the CRC field at the end of a frame (4 bytes for Ethernet/PPP-4, 2 bytes for PPP-2) |
| Internet checksum | "the IP checksum" | RFC 1071 one's-complement sum of 16-bit words with end-around carry; cheap in software, weak against reordering and zero insertion |
| End-around carry | "wrap the carry" | Folding the high-order overflow back into the low 16 bits, the defining operation of one's-complement addition on a two's-complement machine |
| Fletcher's checksum | "a better checksum" | A position-weighted two-sum checksum (sum1, sum2) that detects reordering the plain sum misses; still weaker than a CRC |
| Burst error | "a run of errors" | A contiguous span whose first and last bits are flipped; interior bits may or may not be — CRC catches all bursts of length ≤ r |
| Hamming distance | "how many errors are caught" | The minimum number of bit errors that converts one valid codeword into another valid codeword; CRC-32/IEEE has distance 4, CRC-32C has 6 |
| GF(2) | "binary arithmetic" | The two-element Galois field where addition and subtraction both equal XOR — no carries, no borrows, the algebra CRC runs in |

## Further Reading

- **RFC 1071** — A Strategic Survey of the Internet Checksum (Braden, Borman, Partridge), the canonical reference for the one's-complement 16-bit sum.
- **RFC 1146** — New IP Option: Alternate Internet Checksum, including the zero-checksum option for high-reliability links.
- **IEEE 802.3, Clause 3** — Ethernet frame format and the 32-bit FCS using polynomial 0x04C11DB7.
- **RFC 1662** — PPP in HDLC-like Framing, defining the 16-bit and 32-bit CRC FCS options for PPP.
- **Peterson & Brown** — "Cyclic Codes for Error Detection," Proceedings of the IRE, January 1961 — the original shift-register CRC hardware.
- **Castagnoli, Braeuer, Herrmann** — "Optimization of Cyclic Redundancy-Check Codes with 24 and 32 Parity Bits," IEEE Trans. Communications, 1993 — the CRC-32C polynomial.
- **Koopman** — "32-Bit Cyclic Redundancy Codes for Internet Applications," DSN 2002 — Hamming-distance analysis showing CRC-32C beats CRC-32/IEEE.
- **Fletcher** — "An Arithmetic Checksum for Serial Transmissions," IEEE Trans. Communications, 1982.
- **Partridge, Mendez, Milliken** — "Host Primer: The Internet Checksum," 1995 — the real-traffic analysis that broke the random-bit assumption.
- **Tanenbaum & Wetherall**, *Computer Networks*, 5th ed., Section 3.2.2 (Error-Detecting Codes).
