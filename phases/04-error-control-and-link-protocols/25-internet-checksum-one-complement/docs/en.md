# The 16-bit Internet checksum in one's complement arithmetic

> The **Internet checksum** (RFC 1071, codified for IP in RFC 894/RFC 791) sits inside the header of every IP, TCP, UDP, ICMP and IGMP packet. It is not a CRC and it is not the parity bit: it is the *one's complement* of the *one's complement sum* of the header's 16-bit words, computed with **end-around carry**. Two properties make it unlike a plain modulo-2^16 sum. First, any carry out of the high bit is folded back into the low 16 bits, so bit-15 overflow can never silently disappear — a defect of the naive sum that leaves the highest-order bit under-protected. Second, one's complement arithmetic has *two* representations of zero (all-0s and all-1s), so the value `0x0000` can legally mean "no checksum present" without a dedicated flag field. The flip side is famous: because the function is a simple commutative sum it fails to detect insertion or deletion of `0x0000` words, reordering of 16-bit words, and many splices of two packets — exactly the patterns buggy (not random) hardware produces. Partridge et al. (1995) showed real traffic is far from random, so undetected errors are more frequent than the long-standing random-data analyses predicted, which is why the data link layer abandons checksums for the polynomial-strength **CRC** while the Internet checksum survives at the network and transport layers as a cheap, software-friendly second defense.

**Type:** Build
**Languages:** Python
**Prerequisites:** Error-detecting vs. error-correcting codes (Phase 4 opening), framing, representation of integers (big-endian words, two's-complement machines)
**Time:** ~75 minutes

## Learning Objectives

- Compute the 16-bit Internet checksum by hand from a sequence of 16-bit big-endian words, performing the end-around carry fold and the final one's complement.
- State precisely why the algorithm is *one's complement* and not a modulo-2^16 sum, and give the two consequences (carry folding, two zeros).
- Implement a sender that zeros the checksum field, computes the value, and writes it back, and a receiver that sums the whole packet and checks for the all-ones (0xFFFF) result.
- Predict which errors the Internet checksum catches and which slip through: isolated bit flips, byte-order errors, 0x0000 insertion, word reordering, byte vs. word swaps.
- Explain why the data link layer prefers a CRC (polynomial code) and why the Internet checksum persists at IP/TCP/UDP/ICMP despite being weaker.
- Read a captured IPv4/TCP header and verify or forge its checksum field using `code/main.py`.

## The Problem

A network engineer captures a TCP packet off the wire and the receiver reports "bad checksum, dropped." The bytes look plausible — sane source and destination ports, a reasonable sequence number — yet the stack refuses it. Worse, a flaky NIC on the path has a habit of duplicating a zero word here and reordering two bytes there; some packets get through that shouldn't, and others get thrown away. To diagnose she must know exactly what the Internet checksum does and does not promise, how it is laid out in the header, and how a sender composes it versus how a receiver verifies it. The mystery: the same bytes, summed differently, give different answers — and a 16-bit sum that "looks right" can still be wrong. This lesson builds exactly the calculator her packet analyzer uses.

## The Concept

### Where the checksum lives: header fields, byte by byte

The Internet checksum is a 16-bit field. Its position depends on the protocol. In an **IPv4** header (RFC 791) it occupies bytes 10–11, immediately after the TTL/Protocol byte pair; the rest of the 20-byte base header — Version/IHL, Total Length, Identification, Flags/Fragment Offset, TTL, Protocol, source and destination addresses — is the input, with the checksum field itself set to `0x0000` during computation. **TCP** (RFC 9293) places its 16-bit checksum field after the Urgent Pointer and before the options; the TCP checksum covers the TCP header *plus* the TCP payload *plus* a 12-byte **pseudo-header** that folds in the IP source, destination, protocol (6), and TCP length — so a checksum failure can mean an IP-layer corruption the IP checksum missed. **UDP** (RFC 768) mirrors this with its pseudo-header using protocol 17. **ICMP** and **IGMP** also use the same 16-bit Internet checksum, computed over their own messages. Every one of them uses one machine's complement sum and folding.

### What "one's complement arithmetic" actually means here

On paper one's-complement arithmetic negates a number by inverting every bit (negative of *n* is `~n`), and it has two zeros — all-0s (`+0`) and all-1s (`−0`). Modern CPUs are *two's*-complement machines, where negation flips bits and adds one. RFC 1071's practical recipe collapses the distinction: compute the ordinary two's-complement sum of the 16-bit words into a register wider than 16 bits, then **fold the carry** back into the low 16 bits until no carry remains. That fold is the whole "one's complement" machinery in implementation form — it is exactly the end-around carry that distinguishes the operation from a modulo-2^16 sum, where a carry out of bit 15 would be discarded and the highest-order bit would be under-protected.

### The algorithm step by step

The sender prepares a byte buffer whose length may be odd — odd-length data is zero-extended by appending one `0x00` byte for the computation only; nothing is sent over the wire. With the checksum field zeroed:

1. Group the bytes into consecutive 16-bit **big-endian** words (byte *i* is the high octet of word *i/2*).
2. Sum the words as ordinary integers into a 32-bit (or wider) accumulator. Carries accumulate in bits 16–31; nothing is masked yet.
3. **Fold end-around carry**: while the high half (bits ≥ 16) is non-zero, add the high half to the low half. Repeat until the whole value fits in 16 bits. This is the one's-complement sum on a two's-complement machine.
4. Take the **one's complement** (bitwise NOT) of the 16-bit result. That is the checksum value to place in the field.

The receiver does the *same* sum but **with the checksum field still in place**. Because the sender put the complement of the sum there, the receiver's one's-complement sum over the entire packet is `0xFFFF` (all ones), whose one's complement is `0x0000`. Hence the textbook's terse rule: "sum the entire received codeword, data plus checksum; if the result is zero, no error has been detected." `code/main.py`'s `verify_checksum` returns `True` precisely when the folded sum equals `0xFFFF`.

### A worked example: a 20-byte IPv4 header

Take a minimal header with checksum field zero: `45 00 00 14 00 01 00 00 40 06 00 00 7f 00 00 01 7f 00 00 02`. As 16-bit big-endian words this is `0x4500 0x0014 0x0001 0x0000 0x4006 0x0000 0x7f00 0x0001 0x7f00 0x0002`. Adding them as ordinary integers into a 32-bit accumulator:

```
0x4500 + 0x0014 + 0x0001 + 0x0000 + 0x4006
       + 0x0000 + 0x7f00 + 0x0001 + 0x7f00 + 0x0002 = 0x0001831E
```

The accumulator is `0x0001831E` — bits above 16 carry. **Fold end-around carry** once: `0x831E + 0x0001 = 0x831F`. No bits remain above 16, so the one's-complement sum is `0x831F`. Take the **one's complement**: `~0x831F = 0x7CE0`, which is the value written into the checksum field on the wire. Re-adding that field, the receiver gets `0x831F + 0x7CE0 = 0xFFFF`, whose one's complement is `0x0000` — accept. Run `code/main.py` to see the live trace (raw accumulator → fold → `~sum` → verify), and `assets/internet-checksum-one-complement.svg` for the pipeline drawn end to end.

### Comparison: naive sum vs. one's complement sum

| Property | Modulo-2^16 sum | One's complement sum |
|---|---|---|
| Carry out of bit 15 | Discarded | Folded back into low bits |
| Top-bit coverage | Weak (overflow lost without trace) | Uniform across all 16 bits |
| Number of zeros | One (all-0s) | Two (all-0s = +0, all-1s = −0) |
| "No checksum" sentinel | Needs an extra flag field | Reserved all-0s value, no field needed |
| Implementation on two's-complement CPU | Native | Sum + fold loop, identical cost |

The single observable difference is the fold. Without it, two headers differing only in the high bit of one word could share a checksum whenever that bit's addition overflows; with it, every bit position contributes symmetrically.

### Two zeros, and why one is reserved

One's complement represents zero two ways: `0x0000` (+0) and `0xFFFF` (−0, since `~0x0000 == 0xFFFF`). For protocol design this is a gift — a fixed all-0s pattern can flag "no checksum," letting UDP mark an otherwise optional checksum without stealing a flag bit elsewhere in the header (RFC 768: a UDP sender may emit a zero checksum to disable the check, mostly used for performance on trusted links historically). The receiver, summing a packet with the all-1s −0 still folded in, still produces `0xFFFF` and accepts; the two zeros collapse in the verify rule.

### The failure modes the textbook and Partridge et al. warn about

Because the checksum is a *commutative, associative sum*, it inherits the classic weaknesses of any additive code:

| Corruption | Detected by Internet checksum? | Why |
|---|---|---|
| Single bit flip | Yes | Changes exactly one word's value |
| Multi-bit flips in distinct words | Usually yes (unless they cancel) | Sum shifts; cancellation is the rare case |
| Insertion / deletion of a `0x0000` word | **No** | Adding zero leaves the sum unchanged |
| Reordering of 16-bit words | **No** | Sum is order-independent |
| 8-bit byte swap inside a word (endianness error) | **No** if both bytes identical; usually yes otherwise | Swapping bytes changes the word value unless bytes match |
| Message splice of two valid packets | Often **No** | Two correct halves may share the right sum |
| Burst errors (CRC's specialty) | Unreliable | Not designed for bursts; this is what CRCs are for |

The links-layer **CRC** (polynomial code, see the next lesson) is strong precisely where the checksum is weak: a CRC divides the frame by a generator polynomial `G(x)` and catches any error polynomial `E(x)` that is not a multiple of `G(x)`, defeating reordering, splices, and many burst patterns. The Internet checksum persists despite these gaps because it is cheap in software, byte-order-tolerant, and computed incrementally as packets cross network layers; it is a reasonable second line of defense, not a primary one.

### Why the data link drops to CRC while the Internet keeps the checksum

The link layer — Ethernet, Wi-Fi, PPP — frames flow over one hop on hardware that can afford a few XOR-and-shift gates, so a **CRC** at the end of each frame (e.g. the Ethernet FCS, CRC-32) gives polynomial-strength protection against the burst noise of real links at near-zero cost. The Internet checksum lives higher: at *every* IP hop the **IP header checksum** is recomputed (TTL decrements each hop, so the sum changes) and verified cheaply in software, and TCP/UDP extend coverage end-to-end across the whole transport segment via the pseudo-header. The division of labor is intentional: weak-but-software-friendly checks where data is touched by code, strong-but-hardware-friendly checks where data is touched by silicon.

## Build It

1. Open `code/main.py`. Read `folded_ones_complement_sum` first: it is the literal RFC 1071 recipe — accumulate into a 32-bit `total`, then `fold_carry` loops `total = (total & 0xFFFF) + (total >> 16)` until no high bits remain.
2. Run `python3 code/main.py`. You will see the 20-byte worked example: the list of 16-bit words, the raw 32-bit accumulator, the folded sum, the `~folded` checksum, the wire header with the checksum written in, and the `verify_checksum` confirmation that the whole packet sums to `0xFFFF`.
3. Inspect the alignment behavior: `_byte_align` pads an odd-length buffer with `0x00` *only for the computation*; nothing is sent over the wire. Toggle the example to an odd length and confirm the checksum still verifies.
4. The second demo, `build_error_detection_demo`, shows three corruptions of a valid packet — `0x0000` insertion (undetected), word swap (undetected), single bit flip (detected). Confirm the printed booleans match the table above.
5. Edit the header bytes in `build_ip_header_checksum_demo`: change one address octet (say `7f 00 00 02` → `7f 00 00 03`) and watch the folded sum and the final checksum both change, then change Total Length from `0x0014` to `0x0028` and confirm the verify still returns `True` after recomputation.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Compute a header checksum | 16-bit words, raw accumulator, fold, `~folded` value | The written checksum makes the whole-header sum `0xFFFF` |
| Verify a captured packet | `verify_checksum` returns True | Folded sum equals `0xFFFF` exactly; one's complement is `0x0000` |
| Diagnose a bad-checksum drop | Byte-by-byte diff between sent and captured header | A single bit flip flips the result; no false "good" on real corruption |
| Predict the undetected cases | `0x0000` insertion and word reorder both still verify | You can name each failure mode and why the sum misses it |
| Re-read UDP/TCP pseudo-header | Source/dest IP, protocol, length, segment | The pseudo-header makes a network-layer change contribute to the transport checksum |
| Justify the link-layer CRC | Comparison of error classes the checksum misses | You articulate that CRCs catch reorder/splice/burst where the sum fails |

## Ship It

Produce one artifact under `outputs/`:

- An annotated checksum trace for a real IPv4 + TCP header you construct, with the checksum field zeroed, the raw 32-bit accumulator, the end-around carry fold, the `~sum` value, and the `0xFFFF` verify step — each labeled (see `assets/internet-checksum-one-complement.svg`).
- A one-page failure-mode card: for each corruption class in the table above, whether the Internet checksum detects it, the one-line reason, and the protocol that would catch it instead (CRC at the link layer, pseudo-header at transport).

Start from the printed output of `code/main.py` and annotate it with the worked numbers.

## Exercises

1. Construct a 20-byte IPv4 header in `code/main.py` with Protocol `0x11` (UDP) and a length of 28. Read off the three intermediate values (raw accumulator, folded sum, final checksum) and confirm the wire header verifies.
2. Take a valid computed packet and **reorder two adjacent 16-bit words** in the data (not the checksum). Show that `verify_checksum` still returns `True`, then explain in one sentence why this is the sum being commutative. Which protocol catches reordering instead, and how?
3. Insert a `0x00 0x00` word into the middle of a valid packet. The Internet checksum does not flag it. Describe a realistic hardware bug that produces exactly this artifact, and state what the pseudo-header's protocol-length field would do to TCP if the same bytes were inserted into a TCP segment.
4. A captured IPv4 packet arrives with TTL decremented by one but the checksum unchanged. Trace exactly which header byte moved, recompute the checksum by folding the new TTL into the old sum, and explain how a router updates the IP checksum *incrementally* without re-suming the whole header (RFC 1624).
5. A UDP sender zero-checksum is meant to disable the check (the `0x0000` sentinel) per RFC 768. Build a valid UDP packet, set the checksum field to zero, run `verify_checksum`, and predict the result — then explain why UDP over IPv6 may *not* use the zero-checksum option, referencing the two-zeros property described in this lesson.
6. Compare the cost model: a link-layer CRC-32 protects 1500-byte Ethernet frames; the Internet checksum protects variable 16-bit words in software. Argue why silicon does the CRC and the CPU does the checksum, and name the one IP-hop operation (TTL decrement) that forces the IP checksum to be recomputed hop-by-hop while TCP/UDP checksums are computed once end-to-end.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Internet checksum | "the IP checksum" | The one's complement of the one's complement sum of 16-bit words, same field in IP/TCP/UDP/ICMP/IGMP (RFC 1071) |
| One's complement sum | "weird addition" | A sum where carry out of the top bit is folded back into the low bits (end-around carry), not discarded |
| End-around carry | "the fold" | `total = (total & 0xFFFF) + (total >> 16)` repeated until nothing overflows; the implementation of one's complement on a two's complement CPU |
| One's complement | "bit-flip negation" | `~n` is the negative of `n`; it also produces two zeros (+0 = all-0s, −0 = all-1s) |
| Positive / negative zero | "two zeros" | `0x0000` and `0xFFFF` both equal zero in one's complement; all-0s is reserved as "no checksum" |
| Checksum field | "where it goes" | 16-bit field at bytes 10–11 of the IPv4 header; zeroed by the sender during computation, restored as the wire value |
| Pseudo-header | "TCP/UDP helper" | IP src, dst, protocol, length summed alongside the transport segment so an IP-layer change can fail the transport check |
| Two's complement | "how CPUs work" | The machine's native arithmetic; one's complement sum is implemented on top of it by ordinary add + fold carry |
| Partridge effect | "checksums are weak" | Real traffic is non-random (bunches of zeros, repeated fields), so undetected errors exceed the random-data analyses |
| Incremental update | "RFC 1624" | Adjusting a checksum by the delta of one changed word rather than re-computing the whole sum; how routers handle TTL decrement |

## Further Reading

- **RFC 1071** — Computing the Internet Checksum (Braden, Mogul, Partridge), the canonical algorithm and the fold-carry recipe.
- **RFC 1624** — Computation of the Internet Checksum via Incremental Update (Rijsinghani), the TTL-decrement shortcut routers use.
- **RFC 791** — Internet Protocol: the IPv4 header layout and the bytes 10–11 checksum field.
- **RFC 9293** — Transmission Control Protocol (TCP), including the TCP pseudo-header over which the checksum is computed.
- **RFC 768** — User Datagram Protocol, with the `0x0000` "no checksum" sentinel and the UDP pseudo-header.
- **RFC 894** — A Standard for the Transmission of IP Datagrams over Ethernet Networks (where the link-layer FCS/CRC sits below the IP checksum).
- Partridge, Stone, et al., "A Report on the Performance of the Internet Checksum," 1995 — the empirical finding that real traffic is not random, weakening the Internet checksum's detected-error guarantees.
- Fletcher, "An Arithmetic Checksum for Serial Transmissions," IEEE Trans. Comm., 1982 — Fletcher's checksum, which adds a positional component the Internet checksum lacks.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 3, Section 3.2.2 (Error-Detecting Codes) and the worked CRC example that follows.