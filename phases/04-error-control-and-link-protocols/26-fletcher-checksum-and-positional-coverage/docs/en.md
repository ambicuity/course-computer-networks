# Fletcher's Checksum and Positional Error Coverage

> A **checksum** is any group of check bits appended to a message so the receiver can recompute them and decide whether the frame is intact. The simplest running-sum checksum — the **16-bit Internet checksum** defined in RFC 1071 and used in the IPv4 header, TCP, UDP, and ICMP — sums 16-bit words in **one's-complement arithmetic** and is the complement of that sum. Its weakness is that it is a *position-independent* sum: deleting a zero word, inserting a zero word, or swapping two words leaves it unchanged, and it gives weak protection against packet splices caused by buggy hardware. **Fletcher's checksum** (Fletcher, 1982) fixes the position blind spot by keeping *two* running sums, `s1` and `s2`, where `s2` adds the running `s1` each step — so the contribution of byte *i* is weighted by `(n − i + 1)`, a positional weighting. Two popular variants ship in real protocols: **Adler-32** (RFC 3309, used in zlib/gzip) and **Fletcher-32** used in **OPNET**-style link-layer frames. The classic failure mode of any pure-sum checksum is a **two-bit error** in both directions (a +1 in one word cancelled by a −1 in another) that the Internet checksum misses but Fletcher catches because the offset positions differ. This lesson builds a runnable comparison of the XOR parity check, the Internet checksum, Fletcher-16/32, and Adler-32, and shows concretely the bursts and swaps each one catches.

**Type:** Build
**Languages:** Python
**Prerequisites:** Parity and the single-bit error model, the Internet checksum (one's-complement sum), the burst-error model and interleaving
**Time:** ~85 minutes

## Learning Objectives

- Compute the 16-bit Internet checksum by hand on a small header and explain why one's-complement end-around carry exists (RFC 1071).
- Distinguish a **position-independent sum** (Internet checksum) from a **position-weighted sum** (Fletcher), and name the specific error class each catches and misses.
- Implement Fletcher-16 (two 8-bit accumulators), Fletcher-32 (two 16-bit accumulators), and Adler-32 (RFC 3309) and verify modulus constants 255, 65535, and 65521.
- Predict, for a swapped-word error and a word-insertion error, which of {Internet checksum, Fletcher-32, Adler-32} detects it and why.
- Relate the bitmask-width argument to burst detection: state why Fletcher-32 with accumulators mod 65535 detects all bursts of length ≤ 16 bits and most longer bursts.
- Read an Ethernet/PPP FCS field (RFC 1662 CRC-32) and explain why links use CRC, not a sum checksum, despite Fletcher's improvement.

## The Problem

A vendor ships a T1 framer whose "FCS" is actually the Internet checksum because the developer copy-pasted the IP-header code. Field reports are vague: occasionally a billing record arrives with one field replaced by bytes from the *next* record on the line. The link has a bit error rate of 10^-7, so random bit flips are rare — but the failures cluster, and they look like whole 32-bit words have been moved around.

When you instrument the line you find the smoking gun: a flaky DMA controller occasionally drops one word and injects a duplicate of an *adjacent* word later in the frame — a **swap**. The Internet checksum of the rearranged frame is *identical* to the original, because addition is commutative and associative: a + b == b + a. The "checksum OK" verdict is a lie. You need a check that is sensitive to *where* each byte sits, not just to *which* bytes are present. That is exactly what Fletcher's checksum was designed for in 1982.

## The Concept

### The Internet checksum: position-independent by construction

RFC 1071 defines the Internet checksum as the one's-complement sum of all 16-bit words of the segment, with the checksum field itself treated as zero during computation, then taking the one's complement of that sum as the stored value. Verification sums every word *including* the stored checksum; a valid frame yields all-ones, whose one's complement is zero.

The crucial property is the one stated in the chapter: **it is a sum.** Because addition commutes and associates, the result is independent of the *order* of the words. Concretely, three error classes slip straight through:

- **Zero insertion / deletion.** Adding or removing an all-zero 16-bit word changes the byte length but not the sum, so the checksum is unchanged. RFC 1071 explicitly relies on the length being protected elsewhere (e.g., the IP Total-Length field).
- **Word swap.** Swapping word *i* and word *j* leaves the sum byte-identical.
- **Compensating two-bit errors.** Flipping bit *p* from 0→1 in word *i* and bit *p* from 1→0 in word *j* adds 2^p to one word and subtracts 2^p from the other, net change zero.

`code/main.py` reproduces all three undetected cases against the Internet checksum so you can see the "0x0000 — no error detected" line for a frame that is obviously wrong.

### Fletcher's idea: weight each byte by its position

Fletcher (1982) keeps **two** running sums over the byte stream, both taken modulo a small power-of-two-minus-one:

```
s1 = 0
s2 = 0
for each byte b in message:
    s1 = (s1 + b)        mod M
    s2 = (s2 + s1)       mod M
checksum = (s2 << k) | s1
```

The trick is the second accumulator: because `s2` absorbs every intermediate `s1`, by the end of the message byte *i* (0-indexed, length *n*) has contributed to exactly `(n − i)` of the `s1` updates that fed `s2`. So byte *i* is effectively multiplied by a weight of `(n − i + 1)` inside `s2`. Move that byte to a different position and its weight changes — a swap is no longer invisible. This is the chapter's "positional component."

| Variant | Accumulator width | Modulus M | Field width | Detected bursts |
|---|---|---|---|---|
| Fletcher-16 | 8 bit | 255 | 16 bit (s1 ‖ s2) | all bursts ≤ 8 contiguous bits |
| Fletcher-32 | 16 bit | 65535 | 32 bit (s1 ‖ s2) | all bursts ≤ 16 contiguous bits |
| Adler-32 (RFC 3309) | 32 bit | 65521 (largest prime < 2^16) | 32 bit | bursts ≤ 16 bits, plus a strong `s1 = sum + 1` bias |

The modulus M = 2^k − 1 (a Mersenne number) is chosen so that adding an end-around carry into the low bits is equivalent to adding it back, exactly the one's-complement trick RFC 1071 uses — but now applied to *two* accumulators. Adler-32 swaps M = 65535 for the prime 65521 for slightly better dispersion at the cost of a division by a non-Mersenne constant; it also seeds `s1 = 1` rather than 0 so that a string of zero bytes is not the (weak) all-zero signature.

### Worked example: Fletcher-16 on `{0x01, 0x02, 0x03}`

M = 255, message length 3.

| Step | byte | s1 = (s1+b) mod 255 | s2 = (s2+s1) mod 255 |
|---|---|---|---|
| 0 | 0x01 | 1 | 1 |
| 1 | 0x02 | 3 | 4 |
| 2 | 0x03 | 6 | 10 |

Final checksum = `(s2 << 8) | s1 = (10 << 8) | 6 = 0x0A06`.

Now swap the first and last bytes to `{0x03, 0x02, 0x01}`:

| Step | byte | s1 | s2 |
|---|---|---|---|
| 0 | 0x03 | 3 | 3 |
| 1 | 0x02 | 5 | 8 |
| 2 | 0x01 | 6 | 14 |

Checksum = `0x0E06` — different from `0x0A06`. The Internet checksum (sum = 0x06, stored as complement) would have been identical for both orders. The middle column `s1` is the same (6) because `s1` is a plain running sum; only `s2`, which folds in position, changes. `code/main.py` prints exactly these two traces side by side.

### Detection guarantees and the burst math

For a checksum built from two k-bit accumulators mod M = 2^k − 1, the standard guarantees are (Maxino & Koien, 2009, and Stone et al., 1998):

- **All single-bit errors** are detected (the parity of `s1` flips).
- **All double-bit errors** are detected *unless* they are separated by exactly a multiple of M − 1 positions (the modular cycle), which for Fletcher-16 means a separation of 254 bytes — long messages degrade toward this rare miss.
- **All burst errors of length ≤ k bits** are detected, because a burst that short cannot flip high and low halves of an accumulator in a way that cancels.
- **Probability of an undetected random error** is about 2^−2k (two independent accumulators), versus 2^−k for a plain k-bit sum — roughly 2^−16 for Fletcher-16, 2^−32 for Fletcher-32.
- **Adler-32's `s1 = 1` seed** is a deliberate patch: an all-zero message under Fletcher would give `s1 = s2 = 0`, making zero-insertion invisible. Adler's seed breaks that symmetry.

### Position blindness versus position sensitivity: a decision table

| Error pattern | Internet checksum (RFC 1071) | Fletcher-16/32 | Adler-32 | CRC-32 (RFC 1662) |
|---|---|---|---|---|
| Single bit flip | detected | detected | detected | detected |
| Two-bit, opposite signs, same word | detected (sum changes) | detected | detected | detected |
| Two-bit, opposite signs, different words | **missed** | detected | detected | detected |
| 16-bit burst | detected ~1 − 2^−16 | detected (F-32) | detected | detected |
| Swap two 16-bit words | **missed** | detected | detected | detected |
| Insert/delete one zero 16-bit word | **missed** (sum unchanged) | detected (positions shift) | detected | **missed** (CRC is linear in length if you don't fix block length) |
| Two 32-bit words swapped, identical bytes | misses | **missed** (identical bytes ⇒ identical weights) | **missed** | misses |

The two bottom rows are the subtle part. Fletcher beats the Internet checksum on *move* errors but inherits from any checksum a fundamental ceiling: a CRC computed over a *fixed-length* frame is a strong polynomial residual, but a pure sum — even a position-weighted one — cannot beat the 2^−(2k) random-error bound and is defeated by any two errors whose weighted contributions cancel mod M. That is why physical links (Ethernet 802.3, PPP RFC 1662, HDLC) use a **CRC-32** generator polynomial 0x04C11DB7 rather than any checksum, despite Fletcher's gains.

### Where Fletcher and Adler actually live

| Protocol / format | Field | Algorithm | Reference |
|---|---|---|---|
| IPv4 / TCP / UDP / ICMP header | Header Checksum | Internet (one's-complement sum) | RFC 1071, RFC 791, RFC 793 |
| zlib compressed stream | Adler-32 footer | Adler-32 | RFC 3309, zlib format RFC 1950 |
| gzip member footer | CRC-32 | CRC-32 | RFC 1952 |
| Ethernet 802.3 frame trailer | FCS (4 bytes) | CRC-32 | IEEE 802.3 |
| PPP on HDLC-like framing | FCS (2 or 4 bytes) | CRC-16 or CRC-32 | RFC 1662 |
| ITU-T X.25 / T.30 data blocks | Block check | Fletcher-16 / CRC | ITU-T X.25 |
| SCTP base checksum (pre-2002) | Adler-32 | Adler-32 | RFC 2960; later weakened to CRC-32c in RFC 3309 |
| OSI transport class TP4 | Checksum | Fletcher / arithmetic | ISO 8073 |

Note the historical arc: SCTP started with Adler-32 (RFC 2960) and was *downgraded* to CRC-32c (Castagnoli) in RFC 3309 precisely because Adler-32's `s1 = 1` seed gave weak dispersion on short SCTP chunks. The lesson: a position-weighted sum is better than a plain sum but worse than a polynomial residual, and protocol designers migrate toward CRC when the cost of a missed error exceeds the cost of the division.

### Reading a frame checksum field

A real Ethernet frame ends in a 4-byte FCS, transmitted least-significant byte first:

```
| Dst MAC | Src MAC | EtherType | Payload (46–1500) | FCS (CRC-32) |
   6 B       6 B        2 B              N B              4 B
```

Fletcher-16 frames (rare in modern Ethernet but seen in lightweight serial protocols) pack the two 8-bit accumulators as `(s2 << 8) | s1`, also little-endian. The receiver recomputes from the data and compares; with a sum checksum it can equivalently fold the stored value into the running sum and check for the all-zero/all-one sentinel, the same RFC 1071 trick. `code/main.py` shows both verification styles (compare-the-word and fold-and-check-sentinel) on the same data so you can read either form in the field. The SVG (assets/fletcher-checksum-and-positional-coverage.svg) diagrams the two-accumulator dataflow and the position-weight that distinguishes Fletcher from a flat sum.

## Build It

1. Open `code/main.py`. It implements `internet_checksum()`, `fletcher16()`, `fletcher32()`, and `adler32()` against the exact RFC 1071 / Fletcher-1982 / RFC 3309 definitions, plus a small `Frame` helper that prints the byte layout.
2. Run it: `python3 code/main.py`. The demo prints the Internet checksum, Fletcher-16, Fletcher-32, and Adler-32 for a fixed 32-byte test message, then re-prints all four after a word-swap and a zero-word-insertion, marking each one DETECTED or MISSED.
3. Inspect the worked Fletcher-16 example (`0x0A06`) and confirm it matches the table above when you re-derive by hand on `{1, 2, 3}`.
4. Edit the `BURST` constant in the demo to inject a 16-bit contiguous burst and observe that Fletcher-32 and Adler-32 flip while the Internet checksum can still miss if the burst straddles a word boundary symmetrically.
5. Push the message length past 4080 bytes and notice the `fletcher16()` detection probability dropping — that is the modulus-cycle caveat (M − 1 = 254 positions) called out by Maxino & Koien.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm an Internet checksum misses a word swap | Swap two non-equal 16-bit words; Internet checksum stays 0x0000, Fletcher-32 changes | The receiver should *not* trust "checksum OK" when the byte order has changed |
| Show Fletcher detects position change | Fletcher-32 differs between original and byte-swapped frame by a non-zero delta in the `s2` half | The `s2` half is what moved; `s1` alone would equal the flat sum |
| Demonstrate the all-zero Adler seed | Run Adler-32 on an all-zero payload then on a one-non-zero-byte payload | Adler never returns all-zero for non-empty input (the `s1 = 1` seed) |
| Justify using CRC-32 on a link, not Fletcher | Run all four on a compensating two-word error designed to cancel Fletcher-32 mod 65535 | CRC-32 still flips; Fletcher-32 misses — link layer must use polynomial residual |
| Read a PPP FCS verdict | Frame payload + stored FCS; fold-and-check sentinel yields 0x0000 (CRC) or 0xFFFF (sum) | Distinguish the sum sentinel (one's-complement) from the CRC residual (zero) |

## Ship It

Produce one artifact under `outputs/prompt-fletcher-checksum-and-positional-coverage.md`:

- A captured run of `code/main.py` on a 64-byte message, annotated with the detected/missed verdict for each of: single-bit flip, compensating two-word error, word swap, zero-word insertion, and a 16-bit burst.
- A one-page decision card: given a link with bit error rate 10^-7 and a DMA controller known to drop words, choose Internet checksum vs Fletcher-32 vs Adler-32 vs CRC-32, with the reason in one sentence each.
- A worked-by-hand Fletcher-16 trace on `{0x10, 0x20, 0x30}` showing s1 and s2 at each step and the final 16-bit checksum, as a check against the program's output.

Start from the printed output of `code/main.py` and annotate it with the failure mode each test exercises.

## Exercises

1. A 40-byte message has its 2nd and 38th bytes (0-indexed) flipped in opposite directions. Compute the Internet checksum delta and the Fletcher-16 `s2` delta by hand. Which detects the error, and why does the 36-byte gap matter for Fletcher-16's modulus cycle?
2. Implement the *fold-and-check* verification form for Fletcher-32: fold the stored 32-bit checksum into the running accumulators and show the sentinel the receiver should see for a good frame. Compare it to RFC 1071's all-ones sentinel.
3. The SCTP working group moved from Adler-32 (RFC 2960) to CRC-32c (RFC 3309). Cite the specific weakness of Adler's `s1 = 1` seed on short SCTP DATA chunks that motivated the change, and verify it with a program run.
4. Construct a compensating two-word error that defeats Fletcher-32 but is caught by CRC-32. Give the exact byte positions and values, and prove the Fletcher `s2` delta is zero mod 65535.
5. A buggy serializer occasionally duplicates the *first* 16-bit word of a payload and drops the *last* word. Predict the verdict for the Internet checksum, Fletcher-32, and Adler-32, then confirm with `code/main.py`.
6. You are designing a low-power serial bus where each 1 kB frame must be checked with a 16-bit field. Defend or attack the choice of Fletcher-16 over CRC-16-CCITT, citing the burst detection bounds and the modulus-cycle caveat for messages near 4080 bytes.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Internet checksum | "the IP checksum" | RFC 1071 one's-complement sum of 16-bit words; position-independent, so order changes and zero insert/delete are invisible |
| One's-complement sum | "weird addition" | Sum mod 2^k with end-around carry; equivalently, add the overflow bits back into the low half, so a + b treats negatives as bitwise complements |
| Fletcher's checksum | "two sums" | A pair of running accumulators where the second folds in the first, weighting byte *i* by `(n − i + 1)` so position changes are detectable |
| s1 / s2 | "the running totals" | `s1` is a plain running sum (same as a flat checksum); `s2` is the position-weighted accumulator that adds `s1` every step |
| Adler-32 | "zlib's checksum" | RFC 3309 variant of Fletcher-32 with prime modulus 65521 and `s1 = 1` seed, breaking the all-zero-message symmetry Fletcher inherits |
| Position-independent | "order doesn't matter" | A sum's value is unchanged by reordering its operands — the property the Internet checksum inherits and Fletcher breaks |
| Burst error | "a run of bad bits" | A contiguous stretch of bit flips, length measured from the first to the last flipped bit (interior bits may be correct) |
| Modulus cycle | "the Fletcher weakness" | Two errors separated by a multiple of M − 1 positions cancel inside `s2` mod M, capping detection on long messages |
| CRC / FCS | "frame check sequence" | Polynomial division remainder over GF(2); a length-bounded strong residual the link layer uses because sums, even position-weighted, cancel too easily |
| Sentinel value | "the all-zero/all-ones trick" | A packed value (e.g., 0x0000 "no checksum", 0xFFFF for a folded Internet checksum) that lets one field do double duty without a separate "present" bit |

## Further Reading

- **RFC 1071** — Computing the Internet Checksum (Braden, Mogul, Postel), the one's-complement 16-bit sum used by IPv4/TCP/UDP/ICMP.
- **RFC 3309** — Stream Control Transmission Protocol Checksum Change (Adler-32 → CRC-32c), with the explicit analysis of Adler's weakness on short chunks.
- **RFC 1950** — ZLIB Compressed Data Format, where Adler-32 is the stream footer checksum.
- **J. G. Fletcher**, "An Arithmetic Checksum for Serial Transmissions," IEEE Transactions on Communications, COM-30(1), January 1982 — the original two-accumulator algorithm.
- **M. N. Maxino & D. J. Koien**, "The Effectiveness of Checksums and CRCs in Networks with Bursts of Errors," 2009 — empirical burst and random-error rates for Internet, Fletcher, Adler.
- **J. Stone et al.**, "Performance of Checksums and CRCs over Real Data," IEEE/ACM TON, 1998 — the Partridge-style observation that real data is not random, and the case for CRC over Adler.
- **RFC 1662** — PPP in HDLC-like Framing, which defines the CRC-16 and CRC-32 FCS used on PPP links.
- **IEEE 802.3** — the 32-bit FCS polynomial 0x04C11DB7 used in every Ethernet frame trailer.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 3, Section 3.2.2 on checksums and the move to CRC.