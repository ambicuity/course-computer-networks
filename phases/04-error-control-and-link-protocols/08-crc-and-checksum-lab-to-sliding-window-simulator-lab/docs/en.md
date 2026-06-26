# CRC and Checksum Lab to Sliding Window Simulator Lab

> Error detection and reliable delivery are two halves of the same data-link job, and this capstone wires them together end to end. You build a bit-level **CRC-32** generator over the IEEE 802.3 polynomial `0x04C11DB7` (left-shift LFSR, reflected input/output, final XOR `0xFFFFFFFF`), then the **16-bit one's-complement Internet checksum** from RFC 1071 that TCP/UDP/IP carry. You then feed those detectors into a **Go-Back-N** and **Selective Repeat** sliding-window simulator with a configurable bit-error rate, sequence-number field width, retransmission timer, and window size `W`. You will watch the classic failure modes appear: GBN's full-window retransmission storm on a single loss, Selective Repeat's ambiguity when `W > 2^(m-1)`, and the checksum's blindness to byte-swapped 16-bit words. The deliverable is one runnable Python program plus a throughput table that shows why `W` must cover the bandwidth-delay product. Everything is stdlib-only and offline — no captures, no pip, no sockets.

**Type:** Build
**Languages:** Python (standard library only)
**Prerequisites:** Phase 04 lessons on framing, parity/Hamming distance, and ARQ; binary/modulo-2 arithmetic; basic probability
**Time:** ~90 minutes

## Learning Objectives

- Compute CRC-32 (IEEE 802.3) by hand and in code using modulo-2 polynomial division, and verify it against Python's `binascii.crc32`.
- Implement the RFC 1071 16-bit one's-complement checksum, including the end-around carry, and state two error patterns it cannot detect.
- Compare CRC and checksum on detection strength: burst-error coverage, undetected-error probability, and CPU cost.
- Implement Go-Back-N and Selective Repeat over a lossy channel, and explain why each behaves differently on a single mid-window loss.
- Derive the sequence-number constraint `W ≤ 2^m − 1` (GBN) and `W ≤ 2^(m−1)` (SR), and reproduce the SR aliasing bug when it is violated.
- Size the window from the bandwidth-delay product and read throughput off the simulator's output.

## The Problem

A storage appliance ships frames over a noisy 1 Gbps link with a 5 ms one-way delay. Users report that large transfers crawl at a fraction of line rate, and once an hour a file arrives corrupted but the receiver's CRC counter shows zero errors. Two separate bugs hide in that one sentence.

The slow transfer is a window-sizing problem: the sender uses a stop-and-wait-like window of a few frames, so it spends most of its time idle waiting for ACKs across a fat pipe. The silent corruption is an error-detection problem: somewhere a weaker 16-bit checksum is doing the work a 32-bit CRC should be doing, and it is missing a class of errors. To fix either, an engineer has to reason at the bit level (what does the detector actually catch?) and at the protocol level (how many frames can be in flight, and what happens on loss?). This lab builds both halves so the two failure modes become visible and reproducible instead of mysterious.

## The Concept

### Error detection vs. error correction

Data-link error control splits into two strategies. **Forward error correction** (Hamming codes, Reed-Solomon) adds enough redundancy to *repair* bit flips at the receiver. **Error detection plus retransmission (ARQ)** adds only enough redundancy to *notice* corruption, then asks for a resend. CRC and the Internet checksum are detection codes; the sliding window is the retransmission machinery. This lesson is the ARQ branch end to end: detect, then recover.

A detection code maps a `k`-bit message to a `k+r`-bit codeword. Its strength is measured by the minimum Hamming distance `d` between valid codewords: it detects up to `d−1` bit errors and any burst shorter than `r+1` bits. CRC-32 guarantees detection of all bursts ≤ 32 bits and has Hamming distance ≥ 4 over typical frame sizes; the 16-bit checksum is far weaker.

### CRC-32 as modulo-2 polynomial division

A CRC treats the message bits as coefficients of a polynomial `M(x)` over GF(2). You append `r` zero bits, divide by a fixed generator polynomial `G(x)` using XOR (modulo-2, no carries), and the remainder `R(x)` is the CRC. The transmitted codeword `T(x) = M(x)·x^r + R(x)` is exactly divisible by `G(x)`, so the receiver re-divides and expects a zero remainder.

IEEE 802.3 (Ethernet) CRC-32 uses:

| Parameter | Value |
|---|---|
| Polynomial (normal) | `0x04C11DB7` |
| Width | 32 bits |
| Initial value | `0xFFFFFFFF` |
| Input reflected | yes (LSB-first) |
| Output reflected | yes |
| Final XOR | `0xFFFFFFFF` |
| Residue (good frame) | `0xC704DD7B` (or 0 after the XOR-out convention) |

`code/main.py` implements this bit-by-bit so you can see the LFSR shift, and cross-checks every result against `binascii.crc32`. Worked micro-example over the smaller CRC-4 generator `x^4+x+1` (`0b10011`): message `1101` becomes `1101 0000`; dividing by `10011` modulo-2 leaves remainder `1001`, so the frame on the wire is `1101 1001`. Flip any single bit and the remainder is nonzero — the receiver rejects it.

### The 16-bit Internet checksum (RFC 1071)

TCP, UDP, IP, and ICMP carry a 16-bit one's-complement checksum. The algorithm: treat the data as a sequence of 16-bit big-endian words, sum them in one's-complement arithmetic (every carry out of bit 15 is added back into bit 0 — the *end-around carry*), then take the one's complement of the sum. The receiver sums all words including the checksum field; a correct packet yields `0xFFFF`.

```
words:   0x4500 0x003C 0x1C46 0x4000 0x4006 0x0000 ...
sum16  = fold_carries(Σ words)
cksum  = ~sum16 & 0xFFFF
verify = (Σ words_with_cksum) == 0xFFFF
```

Its weakness is structural and important: because addition is commutative and the words are only 16 bits, the checksum **cannot detect a reordering of 16-bit words**, and it misses many cases where one word increases while another decreases by the same amount. It also cannot catch a swap that leaves the modular sum unchanged. CRC-32, being a polynomial remainder, is sensitive to position and catches all of these. The SVG (`assets/crc-and-checksum-lab-to-sliding-window-simulator-lab.svg`) shows both pipelines side by side and marks the checksum's blind spot.

### Detector comparison

| Property | 16-bit Internet checksum | CRC-32 (802.3) |
|---|---|---|
| Width / overhead | 16 bits | 32 bits |
| All single-bit errors | yes | yes |
| Burst errors ≤ width | yes (≤16) | yes (≤32) |
| Reordered 16-bit words | **no** | yes |
| Undetected-error probability | ~2⁻¹⁶ | ~2⁻³² |
| Cost | very cheap (adds) | table-driven shifts |
| Where used | TCP/UDP/IP, RFC 1071 | Ethernet FCS, PPP, PNG, zip |

The takeaway from the opening scenario: a CRC in the Ethernet FCS would have flagged the corruption the application-layer checksum missed.

### Sliding window: the sequence-number field

A sliding-window sender may have up to `W` unacknowledged frames "in flight." Each frame carries a sequence number in an `m`-bit field, so numbers wrap at `2^m`. The window slides forward as ACKs arrive. Two protocols share this skeleton but differ in recovery:

- **Go-Back-N (GBN):** receiver accepts only in-order frames and discards anything after a gap, ACKing the last good frame (cumulative ACK). On timeout the sender retransmits the *entire* window from the lost frame. Constraint: `W ≤ 2^m − 1`.
- **Selective Repeat (SR):** receiver buffers out-of-order frames and ACKs each individually; the sender retransmits only the specific timed-out frame. Constraint: `W ≤ 2^(m−1)`.

### Why Selective Repeat needs the tighter bound

If `W > 2^(m−1)`, old and new sequence numbers alias. With `m = 2` (numbers 0–3) and `W = 3`: the sender sends 0,1,2; all three ACKs are lost; the sender times out and resends 0,1,2 while the receiver — whose window has advanced to {3,0,1} — accepts the retransmitted 0 and 1 as *new* data. Duplicate frames are silently accepted as fresh. With `W = 2 = 2^(2−1)` the windows can never overlap a reused number, so the ambiguity vanishes. `code/main.py` reproduces this exact aliasing as a toggle so you see the corrupted receiver buffer.

### Timers, ACKs, and throughput

GBN typically runs one timer for the oldest unacked frame; SR runs a timer per outstanding frame. Sender efficiency for a window of `W` frames over a link with round-trip time `RTT` and frame transmission time `T_f` is:

```
U = min(1, W · T_f / (T_f + RTT))
```

To saturate the link you need `W · T_f ≥ T_f + RTT`, i.e. `W` must cover the **bandwidth-delay product**. For the 1 Gbps / 5 ms-one-way appliance with 1500-byte frames: `T_f = 12000 bits / 1e9 ≈ 12 µs`, `RTT = 10 ms`, so `W ≥ (12µs + 10ms)/12µs ≈ 835` frames. A window of 8 gives under 1% utilization — exactly the "crawls at a fraction of line rate" symptom. The simulator prints utilization so you can confirm the cliff.

## Build It

The work lives in `code/main.py`. Build and verify in this order:

1. **CRC-32.** Implement `crc32_bitwise(data)` with the 802.3 parameters above. Verify every output equals `binascii.crc32(data) & 0xFFFFFFFF`. Then call `crc32_verify` on a frame, flip one bit, and confirm it now fails.
2. **Internet checksum.** Implement `internet_checksum(data)` with the end-around carry and `verify_checksum`. Confirm a clean packet verifies, then swap two 16-bit words and show the checksum still passes (the blind spot) while CRC-32 fails.
3. **Lossy channel.** Implement a channel that drops or corrupts frames at a given bit-error rate with a seeded RNG so runs are reproducible.
4. **Go-Back-N.** Implement sender/receiver state, cumulative ACKs, single timer, and full-window retransmission. Log every send, drop, ACK, and timeout.
5. **Selective Repeat.** Add per-frame buffering and ACKs. Then run the `m=2, W=3` aliasing case and capture the duplicate-accepted-as-new bug.
6. **Throughput.** Sweep `W` and print utilization to find the knee for the configured RTT.

Run it:

```bash
python3 code/main.py
```

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Validate CRC-32 | `crc32_bitwise` output vs `binascii.crc32` | Bit-identical for every test vector, including empty input |
| Expose checksum blind spot | CRC vs checksum after swapping two 16-bit words | CRC fails, checksum passes — you can name the RFC 1071 reason |
| Watch GBN on one loss | Send/timeout/retransmit log | A single drop triggers retransmission of the whole window |
| Watch SR on one loss | Per-frame ACK log | Only the lost frame is resent; others stay buffered |
| Reproduce SR aliasing | Receiver buffer with `m=2, W=3` | A duplicate is accepted as new data; tightening to `W=2` fixes it |
| Size the window | Utilization vs `W` table | Utilization rises to ~1.0 once `W` covers the bandwidth-delay product |

## Ship It

Produce one artifact under `outputs/`:

- The throughput table (`W` vs utilization) for your chosen RTT, with the bandwidth-delay-product calculation that explains the knee.
- A short note pairing each detector with the failure it catches and the one it misses.
- The captured GBN-storm and SR-aliasing logs as annotated evidence.

Start from [`outputs/prompt-crc-and-checksum-lab-to-sliding-window-simulator-lab.md`](../outputs/prompt-crc-and-checksum-lab-to-sliding-window-simulator-lab.md).

## Exercises

1. Take the 16-byte test packet in `main.py`, swap its first two 16-bit words, and run both detectors. The CRC fails and the checksum passes. Explain in one sentence, citing RFC 1071, why the checksum is blind to this.
2. Run GBN with `W=4` and force a drop of frame 1 in a burst of 6. Count the retransmissions and explain why frames 2 and 3 are resent even though they arrived intact.
3. Run SR with `m=3` (numbers 0–7) and `W=4`; confirm correct behavior. Then set `W=5`, violating `W ≤ 2^(m−1)`, and capture the sequence number that aliases.
4. Sweep `W` from 1 to 64 at the appliance's 10 ms RTT and 12 µs frame time. At what `W` does utilization first exceed 0.5? Compare to the bandwidth-delay-product prediction.
5. Set the bit-error rate so that ~30% of frames are corrupted. Compare GBN and SR goodput at `W=8`. Which degrades faster, and why does GBN's cumulative ACK hurt under high loss?
6. Replace CRC-32 with the CRC-4 generator `x^4+x+1` and corrupt frames with random 5-bit bursts. Show a burst that the 4-bit CRC fails to detect, demonstrating the "bursts longer than `r`" limit.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| CRC | "a checksum" | A polynomial remainder over GF(2); position-sensitive, catches all bursts ≤ its width |
| Internet checksum | "the TCP checksum" | RFC 1071 one's-complement 16-bit sum with end-around carry; blind to 16-bit word reordering |
| Generator polynomial | "the magic number" | `G(x)` that divides every valid codeword; `0x04C11DB7` for 802.3 |
| End-around carry | "weird addition" | Folding the carry out of bit 15 back into bit 0 so the sum stays one's-complement |
| Go-Back-N | "resend everything" | Cumulative-ACK ARQ; one loss forces retransmitting the whole window |
| Selective Repeat | "resend just the bad one" | Per-frame ACK/buffer ARQ; needs `W ≤ 2^(m−1)` to avoid aliasing |
| Window size `W` | "how many at once" | Max in-flight frames; must cover the bandwidth-delay product for full link use |
| Sequence space `2^m` | "the counter" | The wrap-around range of the `m`-bit seq field that bounds `W` |

## Further Reading

- RFC 1071 — *Computing the Internet Checksum* (one's-complement algorithm and optimizations).
- RFC 1141 / RFC 1624 — incremental update of the Internet checksum (the byte-arithmetic subtleties).
- IEEE 802.3 — Ethernet Frame Check Sequence (CRC-32) definition.
- RFC 793 — TCP, §3.1 checksum field and sliding-window flow control.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., §3.2 (error detection/correction) and §3.4 (sliding-window protocols: stop-and-wait, GBN, Selective Repeat).
- Kurose & Ross, *Computer Networking: A Top-Down Approach*, §3.4 (rdt and pipelined reliable transfer).
