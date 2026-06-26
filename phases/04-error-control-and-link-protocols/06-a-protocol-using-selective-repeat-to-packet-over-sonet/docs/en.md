# A Protocol Using Selective Repeat to Packet over SONET

> Selective Repeat (Tanenbaum's Protocol 6) keeps a per-frame retransmission timer and buffers out-of-order frames, retransmitting only the one frame whose timer expired — unlike Go-Back-N which discards everything after a gap. The hard correctness rule: with an n-bit sequence number, the sender and receiver windows must each be at most `(MAX_SEQ + 1) / 2`, i.e. `NR_BUFS = 2^(n-1)`, or a delayed retransmission of frame 0 is mistaken for a brand-new frame 0. The same reliable-delivery thinking later shows up on the wire as **Packet over SONET (PoS)**, where PPP (RFC 1661) frames carry IP packets inside the recurring 125 µs SONET payload. A PoS PPP frame begins and ends with the HDLC flag `0x7E`, uses byte stuffing with escape `0x7D` and a `0x20` XOR, fixes Address to `0xFF` and Control to `0x03` (unnumbered mode), and — per RFC 2615 — uses a 4-byte CRC-32 checksum and scrambles the payload with the x^43+1 self-synchronous scrambler so a long run of zeros cannot break SONET clock recovery. This lesson connects the windowing math to the real frame on the fiber.

**Type:** Build
**Languages:** Python, Wireshark
**Prerequisites:** Sliding-window basics (Go-Back-N, Phase 4 · 05), CRC error detection (Phase 4 · 02). SONET/OC-N basics are introduced in this lesson.
**Time:** ~90 minutes

## Learning Objectives

- Derive why Selective Repeat requires `window <= (MAX_SEQ + 1) / 2` and show the concrete failure when the rule is violated with a 3-bit sequence number.
- Trace a frame through Protocol 6: the `between()` window test, the `arrived[]` bitmap, in-order delivery to the network layer, and per-frame timers.
- Lay out the PPP-over-SONET frame field by field (Flag, Address, Control, Protocol, Payload, Checksum) with exact byte values and sizes.
- Apply PPP byte stuffing/destuffing: turn `0x7E` and `0x7D` in the payload into escape sequences and reverse it.
- Explain why RFC 2615 mandates a 4-byte CRC-32 and payload scrambling on SONET, and what symptom appears if scrambling is disabled.
- Walk the LCP link state machine (DEAD → ESTABLISH → AUTHENTICATE → NETWORK → OPEN → TERMINATE) and identify which packets drive each transition.

## The Problem

You are debugging a long-haul OC-48 (2.488 Gbps) backbone link between two IP routers running Packet over SONET. The link "works" but throughput collapses whenever the bit error rate rises during bad weather. A junior engineer suggests "just retransmit everything after a lost frame." On a fat, high-latency pipe that is exactly the wrong answer: Go-Back-N would re-send a whole window of 1500-byte frames for every single error. Meanwhile a packet capture shows occasional frames the receiver silently drops, and once a month the link mysteriously loses synchronization and resets — always right after an application streams a large block of zero-filled data.

Two distinct mechanisms explain everything here: the retransmission strategy (Selective Repeat vs Go-Back-N) governs how much bandwidth an error costs, and the PoS framing details (scrambling, the `0x7E` flag, CRC-32) govern whether the bitstream stays synchronized and whether errors are even detected. To fix the link you have to reason about both, and tie each symptom to a specific field, timer, or window edge.

## The Concept

### Selective Repeat vs Go-Back-N

Go-Back-N uses a receiver window of size 1: any frame arriving out of order is discarded, forcing the sender to retransmit everything from the lost frame onward. That is cheap to implement (no receiver buffering) but burns bandwidth when errors are frequent.

Selective Repeat (Tanenbaum's **Protocol 6**) gives the receiver a window larger than 1 and a buffer per sequence number. An out-of-order but in-window frame is accepted and stored; only the missing frame is retransmitted. The receiver still delivers packets to the network layer strictly in order — buffered frames wait until the gap is filled.

| Property | Go-Back-N (Protocol 5) | Selective Repeat (Protocol 6) |
|---|---|---|
| Receiver window size | 1 | up to `(MAX_SEQ+1)/2` |
| Out-of-order frames | discarded | buffered in `arrived[]` |
| Retransmission on loss | whole window | single frame (per-frame timer) |
| NAK | optional | one NAK per gap (`no_nak` flag) |
| Receiver buffering cost | none | `NR_BUFS` buffers |
| Best when | errors rare | errors frequent / fat pipe |

### The window-size rule and why it exists

With an n-bit sequence number there are `MAX_SEQ + 1 = 2^n` distinct values. The textbook constant is:

```c
#define MAX_SEQ 7              /* 3-bit sequence: values 0..7 */
#define NR_BUFS ((MAX_SEQ + 1) / 2)   /* = 4 */
```

The receiver window must be **at most half** the sequence space. Here is the disaster the rule prevents, with `MAX_SEQ = 7` and an (illegal) window of 7:

1. Sender transmits frames 0–6. All arrive; receiver advances its window to accept 7, 0, 1, 2, 3, 4, 5.
2. All seven acknowledgements are lost (lightning hits the line).
3. The sender times out and retransmits the *old* frame 0.
4. Frame 0 falls inside the new window, so the receiver accepts the stale duplicate as a *new* frame 0. Data corruption — undetected.

If the window is `(7+1)/2 = 4`, the new window after delivering 0–3 only accepts 4, 5, 6, 7. A retransmitted old frame 0 now falls *outside* the window and is correctly rejected. The figure `assets/a-protocol-using-selective-repeat-to-packet-over-sonet.svg` shows both windows side by side. `code/main.py` includes a `window_overlap` check that flags any `(seq_bits, window)` pair that violates this rule.

### Protocol 6 frame handling

Each arriving data frame runs through this logic (paraphrasing the C in Fig. 3-21):

```text
on frame_arrival(r):
    if r.seq != frame_expected and no_nak:
        send NAK(frame_expected); no_nak = false
    else:
        start_ack_timer()
    if between(frame_expected, r.seq, too_far) and not arrived[r.seq % NR_BUFS]:
        arrived[r.seq % NR_BUFS] = true        # mark buffer full
        in_buf[r.seq % NR_BUFS] = r.info        # store out-of-order frame
        while arrived[frame_expected % NR_BUFS]:
            deliver in_buf[...] to network layer  # in-order delivery
            no_nak = true
            arrived[frame_expected % NR_BUFS] = false
            inc(frame_expected); inc(too_far)     # slide window
```

The `between(a, b, c)` function returns true when `b` is cyclically within `[a, c)`. The `arrived[]` bitmap is the heart of the protocol: it lets the receiver hold frames whose predecessors are still missing. The `while` loop drains the buffer as soon as the gap fills, so the network layer never sees a hole. Acknowledgements are piggybacked: `s.ack = (frame_expected + MAX_SEQ) % (MAX_SEQ + 1)` carries the last in-order frame received; a separate ACK is sent only if the ack timer fires first.

### Per-frame timers and NAKs

In Go-Back-N a single timer covers the oldest unacknowledged frame. In Selective Repeat **every** outstanding frame has its own timer (`start_timer(frame_nr % NR_BUFS)`). When timer *k* expires, only frame *k* is resent. To recover faster than waiting for a timeout, the receiver sends one **NAK** the moment it detects a gap (`r.seq != frame_expected`); the `no_nak` flag ensures at most one NAK per missing frame so a burst of out-of-order arrivals does not trigger a NAK storm.

### From windows to the wire: Packet over SONET

SONET delivers a continuous bitstream at a fixed rate — OC-48 at 2.488 Gbps — organized as byte payloads that recur every **125 µs** whether or not there is data. To carry IP packets you need framing that finds packet boundaries inside that stream. **PPP** (Point-to-Point Protocol, RFC 1661) does this, running on IP routers: `IP → PPP → SONET payload`. PoS is specified by **RFC 2615**.

### The PPP-over-SONET frame format

PPP in unnumbered mode borrows HDLC's frame shape but is **byte-oriented** (byte stuffing) rather than bit-oriented (bit stuffing):

| Field | Size (bytes) | Default value | Purpose |
|---|---|---|---|
| Flag | 1 | `0x7E` (01111110) | Frame delimiter, start and end |
| Address | 1 | `0xFF` (11111111) | "All stations" — avoids link addressing |
| Control | 1 | `0x03` (00000011) | Unnumbered frame |
| Protocol | 2 (or 1) | e.g. `0x0021` IPv4, `0x0057` IPv6 | What the payload carries |
| Payload | variable, default max 1500 | — | The IP packet (scrambled on SONET) |
| Checksum | 2 or **4** | CRC | Error detection |
| Flag | 1 | `0x7E` | Closing delimiter (shared with next frame) |

LCP can negotiate away the constant Address/Control bytes to save 2 bytes per frame, and shrink Protocol to 1 byte. But RFC 2615 **recommends against** that compression on SONET — the links already run fast, and the savings are negligible.

### Byte stuffing, CRC-32, and scrambling

**Byte stuffing.** Because `0x7E` delimits frames, any `0x7E` *inside* the payload must be escaped: replace it with `0x7D 0x5E` (escape byte `0x7D`, then `0x7E XOR 0x20`). The escape byte `0x7D` itself becomes `0x7D 0x5D`. On receive: scan for `0x7D`, delete it, XOR the next byte with `0x20`. This guarantees `0x7E` appears only as a real flag, so a receiver can resynchronize by scanning for it.

**CRC-32.** RFC 2615 mandates the **4-byte checksum**, the same CRC-32 generator (`0x04C11DB7`) used by IEEE 802.3 Ethernet, because the PoS link is the primary error-detection point across the physical, link, and network layers.

**Scrambling.** Before insertion into the SONET payload, PPP scrambles the data by XORing it with the self-synchronous **x^43 + 1** pseudorandom sequence. SONET clock recovery needs frequent 0→1 and 1→0 transitions; a user who sends a long run of zeros would otherwise starve the receiver's PLL of transitions and break synchronization. Scrambling makes an accidental or malicious all-zeros payload statistically indistinguishable from random data. **Disable scrambling and the symptom is exactly the monthly "link resets after a zero-filled transfer" failure from The Problem.**

### The LCP link state machine

Before any IP packet crosses the fiber, the PPP link is negotiated through these states (Fig. 3-25):

```text
DEAD ──carrier detected──▶ ESTABLISH ──options agreed──▶ AUTHENTICATE
  ▲                            │ failed                       │ success
  │ carrier dropped            ▼                              ▼
TERMINATE ◀──── done ──── OPEN ◀──NCP config──── NETWORK
                                                    │ failed → TERMINATE
```

- **DEAD**: no physical-layer connection. **ESTABLISH**: peers exchange **LCP** packets to negotiate options (MRU, checksum size, compression). **AUTHENTICATE**: optional identity check (PAP/CHAP).
- **NETWORK**: an **NCP** per network layer (IPCP for IPv4) assigns parameters such as IP addresses to each end. **OPEN**: data transport — IP packets ride inside PPP frames inside SONET payloads. **TERMINATE**: graceful shutdown back to DEAD.

## Build It

`code/main.py` is a stdlib-only toolkit tying both halves of the lesson together:

1. Run `python3 main.py`. It validates Selective Repeat windows for 2-, 3-, and 4-bit sequence numbers and prints which violate the half-the-space rule.
2. It runs a Selective Repeat receiver simulation: an out-of-order arrival sequence with one loss, watching the `arrived[]` bitmap fill and drain, delivering to the "network layer" in order.
3. It builds a real PPP-over-SONET frame: byte stuffing, Address `0xFF` / Control `0x03` / Protocol `0x0021`, and the 4-byte CRC-32.
4. It runs the x^43+1 scrambler on an all-zeros payload, showing the transition density before and after.
5. Capture a real PPP frame in Wireshark (or open a sample `.pcap`), filter `ppp`, and compare the dissected Address/Control/Protocol bytes against your built frame.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Verify window legality | `(seq_bits, window)` pair vs `2^(n-1)` | You can state the exact duplicate-acceptance failure for an oversized window |
| Trace in-order delivery | `arrived[]` bitmap snapshots per arrival | Buffered frames are released only when the gap fills; network layer sees no holes |
| Decode a PPP frame | Flag/Address/Control/Protocol bytes in Wireshark | `7E FF 03 00 21 ...` parses cleanly; Protocol `0x0021` = IPv4 |
| Validate byte stuffing | Payload bytes `0x7E`/`0x7D` before and after | Each becomes `7D 5E` / `7D 5D`; round-trip destuff restores original |
| Diagnose sync loss | Transition density of scrambled vs raw zeros | Raw zeros have ~0 transitions; scrambled payload is ~50% transitions |

## Ship It

Produce one reusable artifact under `outputs/`:

- A PoS frame-decoding cheat sheet (field → byte value → meaning), or
- A runbook entry: "OC-48 link resets after large transfers → check scrambling / x^43+1", or
- The window-legality calculator wrapped as a one-line CLI, or
- An annotated Wireshark capture of a PPP `ppp.protocol == 0x0021` frame.

Start from `outputs/prompt-a-protocol-using-selective-repeat-to-packet-over-sonet.md`.

## Exercises

1. With a 4-bit sequence number (`MAX_SEQ = 15`), what is the maximum legal Selective Repeat window? Construct the exact acknowledgement-loss scenario that corrupts data if you use a window of 9 instead.
2. A receiver has `frame_expected = 5`, `too_far = 9`, and frames 6 and 8 already buffered (`arrived[]` set for those). Frame 7 arrives, then frame 5 arrives. List the network-layer delivery order and the final window edges.
3. A PPP payload contains the byte sequence `45 7E 00 7D 28`. Show the byte-stuffed output and then destuff it to prove the round trip.
4. You capture a PoS frame starting `7E FF 03 00 21`. Identify each field and the upper-layer protocol. Then explain what `7E FF 03 00 57` would carry.
5. An OC-48 link loses synchronization roughly once a month, always right after a backup job transfers a large sparse (zero-filled) file. Name the missing or misconfigured PoS feature and the RFC that mandates it.
6. Compare the bandwidth cost of one lost 1500-byte frame in Go-Back-N (window 8) vs Selective Repeat on a link with a 40 ms round-trip. Roughly how many bytes does each retransmit?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Selective Repeat | "retransmit only what's lost" | Protocol 6: receiver window > 1, per-frame timers, `arrived[]` buffer, in-order delivery |
| Window-size rule | "use half the sequence numbers" | Window `<= (MAX_SEQ+1)/2 = 2^(n-1)`, or a stale retransmission is accepted as new data |
| Packet over SONET (PoS) | "IP on fiber" | PPP frames (RFC 2615) carrying IP inside the 125 µs SONET payload |
| Flag byte `0x7E` | "the start byte" | HDLC delimiter `01111110`; appears only as a frame boundary thanks to byte stuffing |
| Byte stuffing | "escaping" | Replace `0x7E`→`7D 5E`, `0x7D`→`7D 5D`; destuff by deleting `0x7D` and XOR-ing next byte with `0x20` |
| Unnumbered mode | "no acks" | Address `0xFF`, Control `0x03`; connectionless, unacknowledged PPP (the Internet default) |
| Scrambling | "encryption" | XOR with x^43+1 pseudorandom sequence for SONET clock transitions — not confidentiality |
| LCP / NCP | "the setup" | LCP negotiates link options; per-protocol NCP (IPCP) configures the network layer |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 6th ed., §3.4.3 (Protocol 6 / Selective Repeat) and §3.5.1 (Packet over SONET).
- RFC 1661 — *The Point-to-Point Protocol (PPP)*.
- RFC 1662 — *PPP in HDLC-like Framing* (flag, byte stuffing, FCS details).
- RFC 2615 — *PPP over SONET/SDH* (4-byte CRC-32, x^43+1 scrambling).
- RFC 1663 — *PPP Reliable Transmission* (the rarely-used numbered mode).
- RFC 1332 — *The PPP Internet Protocol Control Protocol (IPCP)*.
- ITU-T G.707 / Telcordia GR-253 — SONET/SDH framing and OC-N rates.
- IEEE 802.3 — CRC-32 generator polynomial `0x04C11DB7` shared with PPP's 4-byte FCS.
