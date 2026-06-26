# Error-Detecting Codes to A Utopian Simplex Protocol

> The data link layer chops the bit stream into frames and attaches a short check field so the receiver can tell a clean frame from a corrupted one. This lesson covers the three error-*detecting* codes used in practice — a single **parity bit** (Hamming distance 2, even parity = XOR of the data bits), the **16-bit Internet checksum** computed in one's-complement arithmetic with an end-around carry (RFC 1071, carried in IPv4/TCP/UDP), and the **Cyclic Redundancy Check (CRC)**, a polynomial code whose remainder under modulo-2 division by a generator `G(x)` becomes the frame's FCS. We work the textbook CRC example: frame `1101011111` with `G(x) = x⁴ + x + 1` yields remainder `0010`, so the transmitted frame is `11010111110010` and the receiver's division gives zero. We name the real generators: IEEE 802.3 / Ethernet CRC-32 is `x³² + x²⁶ + … + 1` (hex `0x04C11DB7`), detects all bursts ≤ 32 bits and all odd-bit errors, but has Hamming distance only 4. Then we build **Protocol 1 ("Utopia")** — a simplex, error-free, no-ACK, no-sequence-number protocol — to show the bare sender/receiver skeleton that every real protocol later wraps in checksums, timers, and acknowledgements.

**Type:** Build
**Languages:** Python, Wireshark
**Prerequisites:** Framing and the structure of a link-layer frame (Phase 4 · 01); binary/XOR arithmetic
**Time:** ~90 minutes

## Learning Objectives

- Compute an even parity bit and a 2-D (row + column) parity block, and state exactly which errors each catches and misses.
- Calculate the 16-bit Internet checksum in one's-complement arithmetic, including the end-around carry fold, and verify a frame by summing data plus checksum to `0xFFFF`.
- Perform CRC generation by modulo-2 polynomial long division, reproducing the `1101011111` / `G = x⁴ + x + 1` example and explaining why `T(x)` is divisible by `G(x)`.
- Name the IEEE 802.3 CRC-32 generator and the four guaranteed-detection properties (single, odd, double, burst) and the residual undetected-error probability `(½)^r`.
- Implement the Utopia sender/receiver and explain why an error-free, infinitely fast receiver needs no checksum, sequence number, ACK, or timer.

## The Problem

A monitoring alert fires: an Ethernet interface is logging rising `rx_crc_errors` and the switch counter `FCS errors` climbs by a few thousand per hour on one fiber pair. The application team only sees occasional retransmits and slightly higher latency — a vague symptom. Your job is to push that symptom down to the link layer and prove what is happening.

To do that you must know what the "check field" at the end of every frame is, how the receiver uses it to decide *accept or discard*, and what corruption it can and cannot catch. Is a single flipped bit always caught? Are two bit errors in the same frame guaranteed caught? What about a 40-bit noise burst? The answer depends entirely on which code is in use — parity, checksum, or CRC — and on the generator polynomial. This lesson builds the math and code so the answers are exact, then strips a protocol to its skeleton (Utopia) so you can see precisely which machinery error control adds on top.

## The Concept

### Why detect instead of correct

Error-*correcting* codes (Hamming, convolutional, LDPC) repair bits in place and earn their cost on noisy wireless links. Over fiber or high-quality copper the bit error rate is tiny, so it is cheaper to *detect* a rare bad frame and retransmit it than to carry correction overhead on every good frame. All three codes below are **linear, systematic block codes**: data bits appear unchanged and a short check field is appended.

### Single parity bit — distance 2

The even parity bit is the modulo-2 sum (XOR) of all data bits. Sending `1011010` in even parity appends a `0` (the codeword already has an even number of 1s) to give `10110100`; odd parity would append `1`. A single parity bit gives a code of **Hamming distance 2**: any single-bit flip produces the wrong parity and is caught, but no error can be corrected, and any *even* number of flips is invisible. See `code/main.py` → `even_parity_bit`.

A single parity bit also fails badly against **burst errors**, where many adjacent bits flip at once. The fix is a 2-D parity block: arrange `k` rows of `n` bits, append a parity bit per row (VRC) and per column (LRC). This reliably detects up to `k` bit errors and any single burst no longer than the number of rows, because a burst hits a *different column* in each row, so the column parity flags it. The probability a burst of length `n+1` slips through is about `(0.5)^n`. See `vrc_lrc_block` in the code.

### The Internet checksum — one's-complement, RFC 1071

The 16-bit Internet checksum (RFC 1071, used by IPv4, ICMP, TCP, and UDP) sums the message as 16-bit words rather than bits. Because it operates on words, it catches error patterns parity misses: flipping the low bit of two different words leaves bit-parity unchanged but adds two 1s to the running sum.

It is computed in **one's-complement** arithmetic. On a two's-complement CPU that means: take the sum modulo 2¹⁶ and add any high-order overflow back into the low bits (the **end-around carry**), then take the bitwise complement. The receiver sums data *and* checksum; an intact frame folds to `0xFFFF`, whose complement is `0x0000`. One's complement has two zeros (`0x0000` and `0xFFFF`), letting `0x0000` mean "no checksum present" without a separate flag. The weakness: reordered 16-bit words and certain compensating errors pass. Fletcher's checksum (1982) adds a position-weighted second sum and is much stronger for similar cost. The steps are: (1) sum all 16-bit words into a 32-bit accumulator; (2) fold carries `(sum & 0xFFFF) + (sum >> 16)` until ≤ 16 bits; (3) one's complement `~sum & 0xFFFF`; (4) verify that `sum(data + checksum)` is `0xFFFF`. See `internet_checksum` and `verify_internet_checksum`.

### CRC — polynomial codes and modulo-2 division

A CRC treats a `k`-bit frame as the coefficients of a degree-`(k−1)` polynomial over GF(2): `110001` is `x⁵ + x⁴ + 1`. Sender and receiver agree on a **generator polynomial** `G(x)` of degree `r`; both its highest and lowest bits must be 1. The algorithm:

1. Append `r` zero bits to the frame, forming `xʳ·M(x)`.
2. Divide by `G(x)` using **modulo-2** long division — subtraction is XOR, no carries or borrows.
3. Subtract (XOR) the `r`-bit remainder from `xʳ·M(x)`. The result `T(x)` is the transmitted frame, now exactly divisible by `G(x)`.

The receiver divides the received frame by `G(x)`. A nonzero remainder means error. The diagram in `assets/error-detecting-codes-to-a-utopian-simplex-protocol.svg` walks this exact division.

**Worked example** (Tanenbaum Fig. 3-9), reproduced by `crc_frame` in `code/main.py`:

| Quantity | Bits |
|---|---|
| Frame `M(x)` | `1101011111` |
| `G(x) = x⁴ + x + 1` | `10011` (r = 4) |
| `xʳ·M(x)` (append 4 zeros) | `11010111110000` |
| Remainder (the CRC) | `0010` |
| Transmitted `T(x)` | `11010111110010` |
| Receiver: `T(x) mod G(x)` | `0` → accept |

If any single bit of `T(x)` flips, e.g. bit 7, the receiver's remainder becomes nonzero (the code prints `11`) and the frame is discarded.

### What a CRC is guaranteed to catch

With an `r`-bit CRC and a well-chosen `G(x)`:

| Error class | Guaranteed caught when |
|---|---|
| Single-bit | `G(x)` has ≥ 2 terms (always, for any real generator) |
| Odd number of bits | `(x + 1)` is a factor of `G(x)` |
| Double-bit (i, j within frame) | `G(x)` does not divide `xᵏ + 1` for any `k` up to the frame length |
| Burst of length ≤ r | `G(x)` has an `x⁰` term |
| Longer burst / multiple bursts | passes undetected with probability ≈ `(½)ʳ` |

The IEEE 802 / Ethernet CRC-32 generator is `x³² + x²⁶ + x²³ + x²² + x¹⁶ + x¹² + x¹¹ + x¹⁰ + x⁸ + x⁷ + x⁵ + x⁴ + x² + x + 1` (hex `0x04C11DB7`). It detects every burst ≤ 32 and every odd-bit error, but its Hamming distance is only 4 for typical sizes; Castagnoli's CRC-32C (`0x1EDC6F41`, used by iSCSI and SCTP) reaches distance 6. CRCs are computed in hardware with shift-register circuits, so every LAN (Ethernet, 802.11) and point-to-point link (packet-over-SONET) carries one in the frame trailer (the FCS field).

### Protocol 1 — A Utopian Simplex Protocol

Now strip everything away to see the skeleton. Utopia (Protocol 1) makes deliberately unrealistic assumptions: data flow in **one direction only** (simplex), both network layers are always ready, processing time is zero, buffers are infinite, and **the channel never damages or loses a frame**. There are no sequence numbers (so `MAX_SEQ` is unneeded), no acknowledgements, no flow control, and exactly one event type: `frame_arrival`.

The sender is an infinite loop: fetch a packet, copy it into the `info` field of a frame, push it to the physical layer — never waiting. The receiver loops: wait for a frame, lift it off the wire, hand its `info` to the network layer. The `seq`/`ack` fields are never read, because there is nothing to check. `code/main.py` models this with `UtopiaChannel`, `sender1`, and `receiver1`; the SVG's right panel lists what Utopia omits.

Utopia is the baseline. Protocol 2 (stop-and-wait) adds flow control; Protocol 3 adds sequence numbers, ACKs, and a retransmission timer to survive a noisy channel — and *that* is where the CRC from the first half of this lesson finally earns its place.

## Build It

1. Run `python3 code/main.py`. Confirm the parity bit for `1011010` is `0`, the Internet checksum verifies and then fails after a single bit flip, and the CRC of `1101011111` is `0010` with a clean-frame remainder of `0`.
2. In `crc_frame`, change the generator to the Ethernet CRC-32 constant `IEEE_802_3_CRC32_GEN` and confirm the appended field is 32 bits wide.
3. Flip a different bit of the transmitted CRC frame and watch `crc_remainder` go nonzero — then flip *two* bits and check whether the generator still catches it.
4. Extend `UtopiaChannel` with a `drop_rate` and observe that `receiver1` silently loses frames — proving why Utopia's "never loses" assumption is load-bearing and motivating Protocol 3.
5. In Wireshark, open any capture, enable **"Validate the IPv4 header checksum"** and **"Validate the TCP checksum"** in protocol preferences, and find a frame; compare the displayed checksum to what `internet_checksum` computes over the same header bytes.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Identify the FCS on the wire | Ethernet frame trailer; switch `rx_crc_errors` / `FCS errors` counters | You point to the 4-byte CRC-32 and explain that rising counts mean physical-layer corruption, not application bugs |
| Verify an Internet checksum | Wireshark "checksum status: good/bad"; bytes summed in `internet_checksum` | Your hand/code computation matches Wireshark's field, including the carry fold |
| Reproduce a CRC by hand | Modulo-2 long division of `xʳM(x)` by `G(x)` | Remainder matches `crc_remainder`; transmitted frame divides to 0 |
| Justify "is two-bit error caught?" | The generator's factorization vs. frame length | You cite the exact detection rule, not "CRCs are strong" |
| Recognize Utopia in real protocols | Sender/receiver event loop with no ACK path | You can name what must be added (seq, ACK, timer, checksum) for a real link |

## Ship It

Produce one artifact under `outputs/`:

- A CRC worksheet that reproduces the `1101011111` / `G = x⁴ + x + 1` division step by step and then redoes it with CRC-32C.
- A one-page runbook: "frame is being discarded" → check FCS/CRC counters → isolate to a cable/SFP/port → confirm with a loopback.
- The decision table above, turned into a reusable "which errors does my code catch?" checklist.

Start from [`outputs/prompt-error-detecting-codes-to-a-utopian-simplex-protocol.md`](../outputs/prompt-error-detecting-codes-to-a-utopian-simplex-protocol.md).

## Exercises

1. Take the byte block `[0x41, 0x42, 0x43, 0x44]`, compute the 16-bit Internet checksum by hand including the carry fold, then confirm with `internet_checksum`. Now swap the first two 16-bit words and show the checksum is unchanged — explain why this is a real weakness.
2. Using `G(x) = x⁴ + x + 1`, generate the CRC for the frame `1010001101`. Then flip bits 3 and 9 simultaneously and determine, by division, whether this particular double error is detected. Tie the answer to the "does `G(x)` divide `xᵏ + 1`" rule.
3. The Ethernet CRC-32 has Hamming distance 4. Construct (on paper) a 4-bit error pattern that this generator would *not* catch, and explain what distance-4 means operationally for a 1500-byte frame.
4. Build a 4×7 two-dimensional parity block. Introduce a burst of 5 adjacent bit errors within one column-spanning region. Show whether the row+column parity catches it, and state the burst length at which detection is no longer guaranteed.
5. Add a 10% `drop_rate` to `UtopiaChannel`. Run 100 frames and report how many the receiver delivers. Then write the two-line change to `receiver1`/`sender1` (a sequence number and an ACK) that would let you *detect* the loss — i.e., the first step from Utopia toward Protocol 3.
6. In a Wireshark capture, deliberately set "Validate the TCP checksum" on and find a frame marked "checksum incorrect (maybe caused by TCP checksum offload)". Explain why offload makes the captured checksum wrong even though the frame on the wire is fine.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Parity bit | "the extra bit for errors" | XOR of the data bits; a distance-2 code that catches every single-bit error and corrects none, blind to even-count errors |
| Checksum | "a hash of the packet" | Here, the 16-bit one's-complement *sum* of 16-bit words (RFC 1071); a weak linear detector, not a cryptographic hash |
| One's-complement / end-around carry | "weird old math" | Overflow above bit 15 is added back into the low bits; gives uniform coverage and two representations of zero |
| CRC / FCS | "the checksum at the end of the frame" | Remainder of modulo-2 division of `xʳM(x)` by generator `G(x)`; the 4-byte Frame Check Sequence in the Ethernet trailer |
| Generator polynomial `G(x)` | "the CRC seed" | Agreed-in-advance degree-`r` polynomial; its factors determine exactly which error classes are guaranteed caught |
| Hamming distance | "how different two codes are" | Minimum bit positions differing between valid codewords; distance `d+1` is needed to *detect* `d` errors |
| Burst error | "a glitch" | A run of bits starting and ending in 1; CRCs catch every burst of length ≤ `r` |
| Utopia (Protocol 1) | "the toy protocol" | Simplex, error-free, no ACK/seq/flow control; the bare sender/receiver loop every real protocol extends |

## Further Reading

- RFC 1071 — *Computing the Internet Checksum* (Braden, Borman, Partridge, 1988).
- RFC 791 — *Internet Protocol*, IPv4 header checksum definition.
- RFC 793 — *Transmission Control Protocol*, TCP checksum (includes the pseudo-header).
- RFC 3309 — *SCTP Checksum Change* — migration from Adler-32 to CRC-32C (Castagnoli).
- IEEE Std 802.3 — Ethernet Frame Check Sequence (CRC-32, generator `0x04C11DB7`).
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 3 §3.2 (error detection and correction) and §3.3.1 (A Utopian Simplex Protocol).
- Koopman, P. (2002), *32-Bit Cyclic Redundancy Codes for Internet Applications* — comparison of CRC-32 and CRC-32C Hamming distances.
- Wireshark User's Guide — checksum validation and offload caveats.
