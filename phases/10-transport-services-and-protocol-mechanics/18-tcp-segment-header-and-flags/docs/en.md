# The TCP Segment Header and Control Flags

> Every TCP segment starts with a 20-byte fixed header (40 bytes with options), then up to 65,495 bytes of payload, then a 16-bit ones'-complement checksum that covers a 96-bit pseudo-header, the TCP header, and the payload (RFC 793, clarified by RFC 1122 and RFC 3168). The header holds the 5-tuple identifiers (16-bit source and destination ports), a 32-bit sequence number for the first data byte, a 32-bit acknowledgement number that names the next byte the sender expects to receive, a 4-bit data offset that pins down where the payload starts, a 6-bit reserved field that is mostly historical, six 1-bit control flags (URG, ACK, PSH, RST, SYN, FIN) plus two newer ECN flags (CWR, ECE) defined by RFC 3168, a 16-bit receive-window advertisement, and a 16-bit Urgent pointer. The SYN flag is the one that starts a connection (consuming one byte of sequence space so it can be acknowledged unambiguously); FIN tears one direction down; RST aborts a connection without ceremony; ACK is set on every segment except the very first SYN; PSH asks the receiver to deliver without buffering; URG marks an out-of-band offset (deprecated by RFC 6093); and CWR/ECE implement Explicit Congestion Notification. You will learn the bit layout, walk through a Wireshark capture flag-by-flag, and use `code/main.py` to pack and unpack the 12-byte header-prefix words.

**Type:** Lab
**Languages:** Python, Wireshark
**Prerequisites:** Lesson 17 (TCP byte stream and 5-tuple), familiarity with hex dumps, basic bitwise arithmetic
**Time:** ~80 minutes

## Learning Objectives

- Reconstruct the 20-byte TCP header byte-by-byte from a hex dump, naming every field and its width.
- Identify each of the eight control flags (CWR, ECE, URG, ACK, PSH, RST, SYN, FIN) in a Wireshark capture and explain the role of each in the connection lifecycle.
- Compute the 16-bit Internet checksum over a synthetic header + payload + pseudo-header and verify it with `code/main.py`.
- Distinguish the 4-bit Data Offset from the 4-bit Reserved field, and explain why an Options field padded to a 32-bit word boundary is required.
- Decide which flags must be set on a SYN, a SYN-ACK, a data segment, a FIN, and an RST.
- Explain how the ECN bits (CWR, ECE) from RFC 3168 fit into the original reserved field without changing the header size.

## The Problem

You are staring at a Wireshark capture and need to determine, without trusting the dissector, whether a segment is the start of a connection, an acknowledgment of data, or a connection reset. The header byte layout looks intimidating — 32 bits here, 16 bits there, single-bit flags wedged between fields of different widths. One wrong assumption about byte order (TCP is big-endian, "network byte order") and every field after that is shifted and wrong.

The deeper problem is that the same byte encodes both the data offset and three flags. If you read the offset wrong, you misalign the payload; if you misread the flag bits, you misread the lifecycle stage of the connection.

## The Concept

### The 20-byte fixed header (RFC 793)

| Offset | Bytes | Field | Meaning |
|---|---|---|---|
| 0 | 2 | Source Port | 16-bit sender port |
| 2 | 2 | Destination Port | 16-bit receiver port |
| 4 | 4 | Sequence Number | First data byte offset (or ISN+1 of SYN) |
| 8 | 4 | Acknowledgement Number | Next byte expected (valid only if ACK=1) |
| 12 | 1 | Data Offset | Header length in 32-bit words (5–15) |
| 12 | 1 | Reserved + Flags | 3 reserved bits + 8 flag bits (CWR ECE URG ACK PSH RST SYN FIN) |
| 14 | 2 | Window Size | 16-bit receive window, scaled by `window scale` option (RFC 1323) |
| 16 | 2 | Checksum | 16-bit ones'-complement over pseudo-header + TCP header + payload |
| 18 | 2 | Urgent Pointer | Offset from SEQ of the last byte of urgent data |

All multi-byte fields are in **network byte order** (big-endian). On a little-endian host you must `ntohl()` and `ntohs()` (or struct-format `!I`, `!H`) before parsing.

### The flag byte at offset 12 (the second byte of the half-word)

| Bit (MSB→LSB) | Name | RFC | Role |
|---|---|---|---|
| 7 | CWR | 3168 | Congestion Window Reduced — sender has reacted to ECE |
| 6 | ECE | 3168 | ECN-Echo — receiver asking sender to slow down |
| 5 | URG | 793 | Urgent pointer is valid (deprecated, RFC 6093) |
| 4 | ACK | 793 | Acknowledgement number is valid (almost always set) |
| 3 | PSH | 793 | Push — deliver data to app without buffering (mostly ignored) |
| 2 | RST | 793 | Reset — abort the connection abruptly |
| 1 | SYN | 793 | Synchronize — open or accept a connection, consumes 1 byte of seq space |
| 0 | FIN | 793 | Finish — sender has no more data, half-closes the direction |

The reserved bits (3 bits between the data offset and CWR) have stayed unused since 1981. They are zero in modern traffic. The lesson here is that **good protocol design reserves space for the next 30 years**, even when critics say it is "wasting bits."

### The Data Offset field

Data Offset occupies the **high 4 bits of byte 12**. It is measured in 32-bit words, so a value of 5 means 5 × 4 = 20 bytes (no options), 6 means 24 bytes (one 32-bit option word), and 15 means the maximum 60-byte header. This is the field that lets the receiver find the payload start; without it, the variable-length Options field would be unparseable.

### The Checksum and pseudo-header

The checksum is computed the same way as UDP's (RFC 1071):

```
checksum = ones_complement_sum(
    pseudo_header  # src IP, dst IP, zero, protocol=6, TCP length
    + tcp_header
    + tcp_payload
)
```

The pseudo-header is **not transmitted** — it is built by the receiver from the IP header. If the IP header is corrupted in transit, TCP's checksum still catches it (because the pseudo-header won't match). This was the original "defense in depth" that justified duplicating part of IP's addressing inside TCP.

### SYN, FIN, and the one-byte rule

A SYN segment carries **no data but still consumes one sequence number**. The reason is that a SYN needs to be acknowledgable: the responder replies with `ACK = ISN_client + 1`, which would be ambiguous if the SYN did not advance the sequence space. FIN behaves the same way: `ACK = ISN_fin + 1` after a FIN means "I saw your FIN," not "I received a zero-byte data segment."

This rule is what makes the three-way handshake unambiguous and is the reason `code/main.py` reports `consumed_seq = 1` for SYN/FIN.

### Options (RFC 793 + many extensions)

Options are TLV-encoded, padded to a 32-bit boundary. Common ones you will see in captures:

| Kind | Length | RFC | Purpose |
|---|---|---|---|
| 0 | — | 793 | End of option list |
| 1 | — | 793 | NOP — pad to next word boundary |
| 2 | 4 | 793 | MSS — `max segment size` this host will accept |
| 3 | 3 | 1323 | Window scale — shift the 16-bit Window field up to 14 bits |
| 4 | 2 | 1323 | SACK permitted — both ends support selective ACK |
| 5 | variable | 2018 / 2883 | SACK blocks — ranges of bytes received out of order |
| 8 | 10 | 1323 | Timestamps — for RTT sampling and PAWS |

### ECN: the two new flags (RFC 3168)

When ECN is negotiated, the IP header's ECN field is set to `11` (CE) instead of a drop, and the IP layer informs TCP. The receiver sets **ECE** in the next ACK, asking the sender to reduce its congestion window. The sender sets **CWR** in the next segment to acknowledge that it has reacted. After this exchange the receiver can clear ECE. The full state machine fits in the existing header without changing the wire format — exactly the kind of incremental deployment Jacobson's original congestion control embodied.

## Build It

Run the header packer / checker offline:

```bash
cd phases/10-transport-services-and-protocol-mechanics/18-tcp-segment-header-and-flags
python3 code/main.py
```

The script:

1. Builds three sample segments — a SYN, a SYN-ACK, and a data segment with the ACK and PSH flags set — and prints them as 20-byte hex dumps.
2. Decodes each dump back into named fields, including the flag byte.
3. Computes the 16-bit Internet checksum over a synthetic pseudo-header + header + payload and shows the value the receiver would compute.
4. Walks the option byte stream for a SYN carrying `MSS=1460`, `Window Scale=7`, `SACK permitted`, and `NOP` padding, and explains how the data-offset field encodes the total header length.

Use `pack_header()` to build your own segments and `decode()` to validate the result against `tcpdump -x`.

## Use It

| What you want to inspect | How `main.py` shows it | What you see in Wireshark |
|---|---|---|
| Which flags are set | `decode_flags(byte)` prints each named flag | "Flags: 0x012 (SYN, ACK)" in the TCP detail pane |
| Header length | `data_offset_field(off)` → bytes | "Header Length: 32 bytes" |
| MSS advertised | `decode_options(...)` → `(kind=2, mss=1460)` | "MSS: 1460" in options pane |
| Checksum correctness | `ones_complement_sum(...)` recomputes | Validate against Wireshark's value; if they match, no corruption |
| Sequence space consumed by SYN/FIN | `consumed_seq('SYN') == 1` | Watch SEQ numbers advance by 1 across a SYN |

## Ship It

Produce a reusable artifact under `outputs/`:

- A printable TCP header field card that names every byte, every flag, and the data-offset encoding.
- The decoded Wireshark capture for a single TCP connection (SYN, SYN-ACK, ACK, data, FIN, FIN-ACK, ACK) with annotations on the role of each flag.

Start from [`outputs/prompt-tcp-segment-header-and-flags.md`](../outputs/prompt-tcp-segment-header-and-flags.md).

## Exercises

1. Given the hex dump `B4 00 00 50 00 00 00 01 00 00 00 02 50 02 FF FF 00 00 00 00`, identify the source port, destination port, sequence number, acknowledgement number, data offset, flags, and window. What kind of segment is it?
2. A SYN segment carries sequence number `1000`. The receiver replies with `ACK = 1001`. Why is the ACK exactly one greater, and what would happen if the SYN did not consume a sequence number?
3. The flag byte is `0x12`. Name each set flag (use the bit layout from the table above).
4. Compute the Internet checksum over `pseudo = src=10.0.0.1 dst=10.0.0.2 proto=6 len=20`, `header = 20 zero bytes`, `payload = b""`. Verify the value with `code/main.py`.
5. Why does the data offset occupy only 4 bits and not 8? What would happen if it were 8 bits?
6. A SYN carries `MSS=1460, Window Scale=3, SACK permitted, NOP, End`. How many option bytes does it use? What is the value of the Data Offset field?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Data Offset | "header length in bytes" | Header length in 32-bit words (5–15), stored in the high 4 bits of byte 12 |
| Reserved | "old unused bits" | 3 bits after Data Offset that have stayed zero since 1981 |
| ACK flag | "this is an ACK" | Acknowledgement number is valid; set on every segment except the first SYN |
| SYN flag | "open a connection" | Synchronize sequence numbers; consumes one byte of seq space |
| FIN flag | "close my direction" | No more data from sender; half-close until peer also sends FIN |
| RST flag | "abort" | Reset the connection immediately; no graceful teardown |
| PSH flag | "deliver now" | Hint to deliver to application without buffering (mostly ignored) |
| ECE / CWR | "congestion signal" | ECN-Echo and Congestion Window Reduced bits (RFC 3168) |
| Checksum | "TCP error check" | 16-bit ones'-complement sum over pseudo-header + header + payload |
| Pseudo-header | "extra checksum bytes" | src IP, dst IP, zero, protocol=6, TCP length — built from IP header at receiver |

## Further Reading

- RFC 793 — Transmission Control Protocol (the original 20-byte header and flag definitions)
- RFC 1122 — Requirements for Internet Hosts (clarifications, bug fixes for the header)
- RFC 1323 — TCP Extensions for High Performance (window scale, timestamps, PAWS)
- RFC 2018 — TCP Selective Acknowledgement Options
- RFC 2883 — An Extension to the Selective Acknowledgement (SACK) Option
- RFC 3168 — The Addition of Explicit Congestion Notification (ECN) to IP and TCP
- RFC 6093 — On the Implementation of the TCP Urgent Mechanism (deprecates URG)
- Wireshark Display Filter reference — `tcp.flags.syn`, `tcp.flags.ack`, `tcp.flags.reset`
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed. — Chapter 6, TCP header field-by-field