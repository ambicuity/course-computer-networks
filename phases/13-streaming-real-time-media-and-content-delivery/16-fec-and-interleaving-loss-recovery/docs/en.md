# FEC and Interleaving Loss Recovery

> The network will drop packets. Forward Error Correction and interleaving let the receiver recover them without waiting for a retransmission.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Phase 13 lessons 01-15 (RTP/RTCP, Jitter Buffering)
**Time:** ~75 minutes

## Learning Objectives

- Explain Forward Error Correction (FEC) using XOR parity packets
- Describe block interleaving and convolutional interleaving
- Quantify the tradeoff between redundancy overhead and loss recovery
- Implement XOR-based FEC encoding and decoding
- Implement block interleaving and show how it converts burst loss to scattered loss

## The Problem

In real-time media, retransmission (ARQ) is often too slow: by the time the retransmitted packet arrives, its playout deadline has passed. The alternative is to send redundant data proactively so the receiver can reconstruct lost packets from what it already has. Two complementary techniques do this: FEC adds parity packets that can repair missing originals, and interleaving spreads consecutive media packets across different transmission slots so a burst loss affects scattered packets rather than a contiguous block.

## The Concept

### XOR-based FEC

For every group of k media packets, send one parity packet computed as the XOR of all k originals. If any single packet in the group is lost, the receiver can recover it by XORing the surviving k-1 originals with the parity packet.

```text
Group: P0, P1, P2, P3  (4 media packets)
Parity: FEC = P0 XOR P1 XOR P2 XOR P3

If P2 is lost:
  P2 = P0 XOR P1 XOR P3 XOR FEC
```

This is a (k+1, k) code: 1 parity can repair 1 loss per group. For 2-loss repair, you need more parity packets (Reed-Solomon codes).

### Overhead

FEC adds 1/k overhead. With k=4, you send 5 packets for every 4 media packets = 25% overhead. The tradeoff: more overhead = better loss recovery but more bandwidth.

### Interleaving

Without interleaving, a burst loss of 3 consecutive packets destroys 3 adjacent media frames, which is perceptually severe (a 60ms gap in audio). With interleaving, those 3 lost transmission slots map to 3 non-adjacent frames, each of which can be partially reconstructed by the decoder's packet loss concealment.

```text
Block interleaver (depth=4, span=4):

Original order:  0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15

Interleaved transmission:
  Row 0:  0  4  8 12
  Row 1:  1  5  9 13
  Row 2:  2  6 10 14
  Row 3:  3  7 11 15

A burst loss of 3 consecutive slots (e.g., 8, 12, 1) hits frames 8, 12, and 1
instead of 8, 9, 10. Each lost frame has intact neighbors for concealment.
```

### FEC + Interleaving combined

Interleaving alone does not recover lost packets; it just spreads the damage. FEC recovers lost packets but fails on burst loss (if 2 packets in the same FEC group are lost, one parity cannot repair both). Combined: interleave first, then apply FEC to the interleaved stream. Burst losses become scattered, and FEC can repair single losses in each group.

## Build It

The script below demonstrates FEC and interleaving with stdlib only:

1. XOR-based FEC encoding (k=4) and decoding with 1-loss recovery
2. Block interleaving (4x4) and deinterleaving
3. Burst loss simulation with and without interleaving
4. FEC recovery with and without interleaving
5. Overhead and recovery rate comparison

```python
# Core idea (see code/main.py)
parity = xor_all(group)          # FEC encode
interleaved = block_interleave(stream)  # interleave
transmit(interleaved + parity_packets)
# On loss:
deinterleaved = block_deinterleave(received)
recovered = fec_decode(deinterleaved)   # repair single losses
```

## Use It

```bash
python3 code/main.py
```

Expected output: FEC encoding/decoding demonstration, interleaving block visualization, burst loss scenarios with and without protection, and a comparison table showing recovery rates at different loss patterns.

## Ship It

- Use the script to explain why FEC alone fails on burst loss and how interleaving fixes that.
- Tune the FEC group size k and interleaving depth to find the optimal overhead for a target loss rate.
- Export the loss/recovery statistics as a CSV for a study artifact.

## Exercises

1. Increase the FEC group size from k=4 to k=8 and compare overhead vs recovery rate.
2. Add a second parity packet per group (2-loss repair) and show the improvement on burst loss.
3. Change the interleaving depth from 4 to 8 and observe how the burst tolerance changes.
4. Simulate random (non-burst) loss and show that interleaving provides no benefit there.
5. Implement a convolutional interleaver and compare its latency with the block interleaver.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| FEC | "Error correction" | Forward Error Correction: sending redundant parity data so the receiver can repair losses without retransmission |
| XOR parity | "A backup packet" | A packet computed as the XOR of k originals; can repair any single lost packet in the group |
| Interleaving | "Shuffling" | Reordering packets before transmission so burst losses are spread across non-adjacent media frames |
| Burst loss | "A dropout" | Multiple consecutive packet losses, which FEC alone cannot repair if they hit the same group |
| Overhead | "Wasted bandwidth" | The extra bandwidth consumed by parity packets, expressed as a percentage of media bandwidth |
| k | "Group size" | The number of media packets covered by one parity packet; larger k means less overhead but worse burst tolerance |
| Block interleaver | "A matrix shuffle" | An interleaver that writes packets row-by-row into a matrix and reads column-by-column |
| Deinterleaving | "Un-shuffling" | Reversing the interleaving operation to restore original packet order at the receiver |

## Further Reading

- [RFC 5109 - RTP FEC](https://www.rfc-editor.org/rfc/rfc5109) - FEC for RTP
- [Reed-Solomon Codes](https://en.wikipedia.org/wiki/Reed%E2%80%93Solomon_error_correction) - multi-loss FEC
- [Interleaving (Wikipedia)](https://en.wikipedia.org/wiki/Interleaving_(data)) - interleaving techniques
