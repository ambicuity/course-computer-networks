# Build an 802.11 data-frame encoder/decoder with four addresses and the Duration/NAV

> An 802.11 data frame is a 34-byte (or 40-byte) MAC header followed by 0 to 2312 bytes of payload and a 4-byte CRC-32 trailer. The 16-bit Frame Control word packs eleven sub-fields: Protocol Version (2 bits, currently 00), Type (2 bits, data = 10), Subtype (4 bits, plain data = 0000), To DS (1), From DS (1), More Fragments, Retry, Power Management, More Data, Protected Frame, and Order. The 16-bit Duration/ID field carries a microsecond reservation that other stations load into their NAV. To DS and From DS pick one of four address modes: in IBSS (00) Addr 1 is the DA, Addr 2 the SA, Addr 3 the BSSID, Addr 4 unused; in From-DS (10) Addr 1 is the DA, Addr 2 the BSSID, Addr 3 the SA, Addr 4 unused; in To-DS (01) Addr 1 is the BSSID, Addr 2 the SA, Addr 3 the DA, Addr 4 unused; in WDS (11) Addr 1 is the RA, Addr 2 the TA, Addr 3 the DA, Addr 4 the SA. The 16-bit Sequence Control splits 4 bits of fragment number with 12 bits of sequence number. The 4-byte FCS is the same CRC-32 (polynomial 0x04C11DB7) used by Ethernet.

**Type:** Build
**Languages:** Python
**Prerequisites:** Python 3.10+, bitwise operators, the IEEE 802 frame concept, the idea of a CRC checksum, IEEE 802 MAC addressing
**Time:** ~90 minutes

## Learning Objectives

- Pack and unpack the eleven Frame Control sub-fields into a single 16-bit word in the exact order Tanenbaum shows in Figure 4-29.
- Distinguish the four address modes (IBSS, To-DS, From-DS, WDS) by reading the To DS / From DS bit pair and place the right address role in each of Addr 1 through Addr 4.
- Express a Duration/NAV reservation in microseconds and reason about what it covers (the current frame, the ACK, plus the next fragment in a burst).
- Encode a sequence number together with a 4-bit fragment number, and understand why the upper 12 bits count MSDUs, not MPDUs.
- Compute and verify the trailing 4-byte CRC-32 FCS, and recognize a tampered frame by recomputing the CRC over the wire bytes.
- Build a parser that walks an arbitrary 802.11 byte string and recovers the Frame Control, addresses, sequence, body, and FCS, then confirms bit-for-bit round-trip with the encoder.

## The Problem

Ethernet has one address format and one frame layout; you put a destination, a source, a length, a payload, and a 4-byte CRC in that order and you are done. 802.11 cannot lean on that simplification, because the radio link sits between a station and an access point, and the access point sits between the station and the rest of the network. The same MAC frame has to be usable in three topologies at once: peer-to-peer inside an ad-hoc IBSS, station-through-AP into a distribution system, and wireless-bridge-to-wireless-bridge in a WDS. The header needs to express which of those topologies it is moving through, and it needs to do so without forcing the radio to retransmit the whole payload when only the addressing has to change.

802.11 solves this with the **To DS** and **From DS** bits and with four address slots that are reused for different roles in each mode. The same two bits, plus a few more in the Frame Control word, also carry the information that other stations need to stay quiet while the exchange is in flight: the **Duration** field doubles as a NAV (Network Allocation Vector) reservation, and a one-bit **More Fragments** flag tells receivers how much longer the burst is going to take. If you cannot read those fields you cannot decode a single packet capture; if you cannot write them, you cannot build a sniffer, a fuzzer, or any test harness that injects data frames at the MAC layer.

The lesson builds a complete stdlib-only encoder/decoder for the 802.11 data frame. The encoder takes a Frame Control word, a Duration, four addresses, a sequence number, and a body, and produces the exact bytes that would appear on the radio after the PLCP preamble. The parser takes a byte string, recovers every field, and verifies the trailing CRC-32 FCS. The lesson also covers the supporting control and management frames the data frame has to coexist with: RTS, CTS, ACK, and beacon.

## The Concept

### Frame Control: eleven sub-fields in 16 bits

The Frame Control field is two bytes. The 802.11 standard numbers the bits low-byte first: bit 0 of byte 0 is the LSB of the word. Eleven sub-fields share those 16 bits, and the layout is the one Tanenbaum prints in Figure 4-29 (page 310 of the 5th edition).

| Bits | Width | Sub-field | Meaning for a data frame |
|------|-------|-----------|--------------------------|
| 0-1  | 2     | Protocol Version | Always `00` for 802.11; reserved for future revisions |
| 2-3  | 2     | Type            | `00` management, `01` control, `10` data |
| 4-7  | 4     | Subtype         | `0000` for a regular data frame; see Table 4-9 for the rest |
| 8    | 1     | To DS           | Frame is destined for the distribution system |
| 9    | 1     | From DS         | Frame is exiting the distribution system |
| 10   | 1     | More Fragments  | Another fragment of the same MSDU follows |
| 11   | 1     | Retry           | This is a retransmission of an earlier MPDU |
| 12   | 1     | Power Management| Sender is entering power-save mode after this frame |
| 13   | 1     | More Data       | AP has additional MSDUs buffered for a dozing station |
| 14   | 1     | Protected Frame | Body is encrypted (WEP, TKIP, CCMP, GCMP) |
| 15   | 1     | Order           | Receiver must process frames strictly in order |

For the data frames we care about, the only sub-fields that are not always zero are Type (always `10`), Subtype (almost always `0000`; `1000` is QoS data, `0100` is Null data, `1100` is CF-Ack), the two DS bits, More Fragments when fragmentation is in use, Retry on a retransmit, and the Protected bit if the body is encrypted. The lesson sticks to Type=10 Subtype=0000, the To DS / From DS bit pair, and the More Fragments bit to keep the encoder tight.

### Duration/NAV: a microsecond reservation

The Duration/ID field is 16 bits but is interpreted in one of two ways. When the high bit is 0, the remaining 15 bits are a positive integer in microseconds; that is the **NAV** value other stations load into their countdown timer. A station that is not the addressed receiver hears the frame, sees a non-zero Duration, sets its NAV to that value, and refrains from transmitting until the countdown finishes. When the high bit is 1, the lower 15 bits hold the AID (Association ID) of a transmitting station during contention-free periods; the lesson ignores that case.

For a data frame, the Duration is the time the current frame, the immediate ACK, and any next-in-burst fragment are going to keep the channel busy. The SIFS and the ACK are accounted for explicitly: 10 microseconds of SIFS plus an ACK frame's worth of air time plus the time to send the next fragment. A short data frame might carry Duration = 44 (a SIFS + 14-byte ACK at 1 Mbps + a small margin) or Duration = 100 (one full slot of contention plus a fragment). The Duration field is one of the few fields whose value depends on the bit rate the sender has chosen, so it is genuinely part of the MAC behavior, not a fixed label.

### The four address slots and the ToDS/FromDS truth table

The big surprise in 802.11 is that the same four 6-byte address slots mean different things depending on the two DS bits. The full truth table is the heart of the lesson:

| To DS | From DS | Mode                  | Addr 1       | Addr 2       | Addr 3       | Addr 4 |
|-------|---------|-----------------------|--------------|--------------|--------------|--------|
| 0     | 0       | IBSS direct (ad-hoc)  | DA           | SA           | BSSID        | not used |
| 0     | 1       | To DS (STA -> AP)     | BSSID        | SA           | DA           | not used |
| 1     | 0       | From DS (AP -> STA)   | DA           | BSSID        | SA           | not used |
| 1     | 1       | WDS (wireless bridge) | RA           | TA           | DA           | SA     |

The abbreviations matter:

- **DA** (Destination Address) is the 802 address the MSDU is ultimately going to.
- **SA** (Source Address) is the 802 address the MSDU came from.
- **RA** (Receiver Address) is the 802 address on the *air interface* that has to receive the MPDU. For a single hop it is the same as the DA.
- **TA** (Transmitter Address) is the 802 address on the *air interface* that is sending the MPDU. For a single hop it is the same as the SA.
- **BSSID** is the 48-bit identifier of the BSS; for an AP it is the AP's own MAC, for an IBSS it is a locally administered random address chosen by the creator of the IBSS.

Addr 4 is only legal in the WDS mode (To DS = From DS = 1), and that mode is the only one where the frame carries all four slots. In every other case, Addr 4 must be absent, and the parser must reject frames that violate that rule. The bit pair `00` is also the only one where Addr 3 is the BSSID, because the frame never crosses a distribution system, so neither the AP nor the wire is in the picture at all.

### Sequence Control: 12 bits of MSDU number, 4 bits of fragment

The 16-bit Sequence Control field is two pieces glued together. The low 4 bits are the **fragment number** and identify which piece of the current MSDU this is (0..15). The high 12 bits are the **sequence number**, an MSDU counter that is incremented by 1 for each new MSDU the station transmits, with wraparound at 4096. Reassembly on the receive side uses the sequence number to group fragments and the fragment number to order them; duplicate detection discards any MPDU whose (sequence, fragment) pair has already been seen for the same receiver.

A non-zero fragment number is meaningful only when the More Fragments bit in the Frame Control is set, except for the very last fragment. Encoding 12+4 in one word uses the layout `seq << 4 | frag`, and a parser extracts them with the inverse shifts.

### Payload and FCS: 0..2312 bytes plus 4 bytes of CRC

The Data field is the MSDU, the payload that was handed to the MAC by LLC. Its size is 0 to 2312 bytes, where 2312 is the classic 802.11 maximum (an 802.3 frame of 1514 bytes plus LLC and SNAP overhead). The first bytes of the MSDU are an LLC/SNAP header that names the higher-layer protocol (typically IP, ARP, or IPv6) so the receiving station can hand the payload to the right handler.

The Frame Check Sequence is a 4-byte CRC-32 with polynomial 0x04C11DB7, computed over every byte from Frame Control through the last byte of the Data field, transmitted low-byte first. It is the same CRC used by classic Ethernet and by PPP, which makes the FCS the most portable piece of 802.11. The receiver recomputes the CRC and compares the four bytes it received against the four bytes it computed; any mismatch is a discarded frame. The lesson's parser raises a `ValueError` on mismatch, which doubles as a tamper detector in the demo.

### Encoding a data frame

Encoding is straightforward once the truth table is in mind. The encoder packs the Frame Control word, writes the Duration, then writes Addr 1, Addr 2, Addr 3, then the Sequence Control, then Addr 4 (only if both DS bits are 1), then the body, then a 4-byte CRC over everything from the Frame Control through the last body byte. The result is the MPDU that would appear on the air after the PLCP preamble is stripped.

Two invariants the encoder enforces up front:

- The body must fit in 2312 bytes, otherwise the MSDU is too large to be a valid 802.11 data frame.
- The Duration must fit in 15 bits (0..32767). The value 32768 is the special CF-period-set marker and is not a NAV reservation.

A third invariant is enforced when the Frame Control is built: the DS bits are 0/1, the Type and Subtype fit their widths, the Protocol Version is 0..3, and the seven flag bits are strictly 0 or 1.

### Parsing a data frame

Parsing is the inverse. The parser pulls the Frame Control word from the first two bytes, decodes the eleven sub-fields, reads Duration, reads Addr 1, Addr 2, Addr 3, reads Sequence Control, and only then decides whether to read Addr 4. The decision is fully driven by the DS bits the parser just decoded, so the parser cannot be tricked into reading a fourth address when only three are present, nor can it accept a frame that claims WDS but is missing the address.

The final step is FCS verification: the parser recomputes the CRC over everything except the trailing 4 bytes, then compares. A mismatch is a hard error.

### Worked example: a From-DS frame

A small From-DS data frame from an AP to a station looks like this on the wire (hex, byte order as transmitted):

```
08 01                  # Frame Control = 0x0108 = protocol 0, type 10, subtype 0,
                       #   to_ds=1, from_ds=0, the rest zero
2c 00                  # Duration = 44 us
ff ee dd cc bb aa      # Addr 1 = aa:bb:cc:dd:ee:ff (the STA)
55 44 33 22 11 00      # Addr 2 = 00:11:22:33:44:55 (the AP / BSSID)
33 22 11 27 00 08      # Addr 3 = 08:00:27:11:22:33 (the SA, the upstream source)
89 00                  # Sequence Control = 0x0089 = fragment 9, sequence 8
68 65 6c 6c 6f 2d ...  # Data = b"hello-802.11-from-the-AP"
xx xx xx xx            # FCS (4 bytes, little-endian)
```

Decoding the Frame Control word `0x0108` little-endian gives the same word as the 16-bit big-endian read `0x0801` if you flip the bytes, but on the wire the LSB comes first, so the Frame Control is parsed as `0x0801`. That splits into protocol=01, type=00, subtype=0000, to_ds=1, from_ds=0, the rest zero — except we have to remember the bit layout: protocol 0..1 is bits 0..1 of the word, type is bits 2..3, subtype is bits 4..7, to_ds is bit 8, from_ds is bit 9, more_frag is bit 10, retry is bit 11, power is bit 12, more_data is bit 13, protected is bit 14, order is bit 15. The encoder and the demo in `main.py` do this for you; the worked example is here so you can check the bit positions with a pen and a hex chart.

## Build It

1. Install nothing — the lesson is stdlib-only Python. Open `code/main.py`.
2. Read the `FrameControl` dataclass. Confirm that `to_word` packs in the order protocol/type/subtype/to_ds/from_ds/more_fragments/retry/power_management/more_data/protected/order and that `from_word` inverts the same bit positions.
3. Skim the `crc32` helper and the `_build_crc_table` table generator. The polynomial 0x04C11DB7 is the 802.11 / Ethernet / PPP CRC-32; the table is the standard right-shift form with no reflection and no final XOR.
4. Build three frames by hand, one per address mode you want to test, using the `DataFrame` dataclass and the `ADDRESS_MODES` table as a checklist:
   - IBSS direct: To DS = 0, From DS = 0; Addr 1 = DA, Addr 2 = SA, Addr 3 = BSSID, no Addr 4.
   - From DS: To DS = 1, From DS = 0; Addr 1 = DA, Addr 2 = BSSID, Addr 3 = SA, no Addr 4.
   - WDS: To DS = 1, From DS = 1; Addr 1 = RA, Addr 2 = TA, Addr 3 = DA, Addr 4 = SA.
5. Run the file: `python3 code/main.py`. The five round-trips print their decoded FC word, the four addresses with their role labels, the sequence and fragment numbers, the Duration, the body, and the FCS check.
6. In the last block, the script tampers with one bit in Addr 1 and re-runs the parser. Confirm that the FCS check rejects the tampered frame with a clear `ValueError`.
7. Try the same FCS tamper on a frame whose last 4 bytes you replace with a freshly computed CRC — the parser will accept it. This is the only way to forge an 802.11 frame at the MAC layer without the key.

## Use It

| Symbol                            | Type                         | Purpose                                                                       |
|-----------------------------------|------------------------------|-------------------------------------------------------------------------------|
| `FrameControl`                    | `@dataclass(frozen=True)`    | Eleven sub-fields, plus `to_word` / `from_word` for the 16-bit FC.            |
| `SequenceControl`                 | `@dataclass(frozen=True)`    | 4-bit fragment + 12-bit sequence packed into 16 bits.                          |
| `MacAddress`                      | `@dataclass(frozen=True)`    | 6-byte 802 address with `from_hex` / `to_hex` helpers.                        |
| `DataFrame`                       | `@dataclass(frozen=True)`    | A complete data frame: FC, Duration, four addrs, sequence, body, no FCS yet.  |
| `DataFrame.to_bytes`              | method                       | Serializes the frame and appends a 4-byte CRC-32 FCS.                         |
| `parse(bytes)`                    | function                     | Inverse of `to_bytes`; raises on short frame, missing Addr 4 in WDS, or bad FCS. |
| `crc32(data)`                     | function                     | The 802.11 / Ethernet / PPP CRC-32 over `data`.                               |
| `build_control(subtype, dur, ra)` | function                     | Builds a 14- to 16-byte control frame (RTS / CTS / ACK).                      |
| `build_beacon(bssid, dur, ts)`    | function                     | Builds a minimal beacon with a stub body.                                     |
| `ADDRESS_MODES`                   | tuple of tuples              | The four-row To DS / From DS truth table.                                     |
| `show_address_modes()`            | function                     | Prints the truth table.                                                       |
| `main()`                          | function                     | Five round-trips and an FCS tamper check.                                     |
| `MAX_BODY = 2312`                 | constant                     | Upper bound on the Data field size, in bytes.                                 |
| `CRC32_POLY = 0x04C11DB7`         | constant                     | The 802.11 CRC-32 generator polynomial.                                        |

## Ship It

- Treat `MAX_BODY` as the hard upper bound. The MAC cannot transmit a body larger than 2312 bytes in a single MPDU; the higher layer is responsible for fragmentation.
- Treat Duration as a 15-bit unsigned value. The high bit is reserved for the AID/Contention-Free mode; your encoder should reject any value above 32767.
- Always validate the To DS / From DS bit pair against the address layout. If the parser says the frame is WDS, the fourth address must be present, and vice versa. Forgetting that check lets an attacker inject a frame that pretends to be a 4-address bridge frame and confuse logging tools.
- The CRC-32 is the only integrity check the MAC gives you. If you build a capture tool, log CRC failures as their own event, not as silent drops — they are the cleanest signal of a noisy radio or a fuzzing attack.
- Match the bit order in the Frame Control to the standard. The 802.11 spec numbers the fields low-byte first, which is why `to_word` and `from_word` use little-endian shifts. Getting the bit order wrong will produce a header that decodes correctly on your machine but is rejected by every real device.
- Keep the parser's FCS check at the end. It is cheap and it is the only way the implementation can tell a real frame from a hand-crafted one.

## Exercises

1. Add a `QoS` data frame to the encoder. Subtype is `1000` and the Frame Control is followed by a 2-byte QoS Control field (TID, EOSP, Ack Policy, TXOP) before the body. Confirm a round-trip with the extended parser.
2. Implement `parse_rts` and `parse_cts`. An RTS frame is 16 bytes: FC (2) + Duration (2) + RA (6) + TA (6) + FCS (4). A CTS or ACK frame is 10 bytes: FC (2) + Duration (2) + RA (6) + FCS (4). Validate the type and subtype on every read.
3. Write a `parse_any(bytes_on_wire)` that looks at the Type and Subtype sub-fields and dispatches to the right parser. Add a `Null` data frame (subtype 4) path that skips the body.
4. Extend the Frame Control to set the Retry bit on the second copy of a data frame, and have the parser detect retransmissions by checking that bit and comparing the sequence number to a small LRU cache.
5. Add a small CLI: `python3 main.py encode --to-ds 1 --from-ds 0 --addr1 aa:bb:... --addr2 ...` prints a hex blob, and `python3 main.py parse <hex>` prints the decoded fields.
6. Compute the on-the-wire Duration for a 100-byte data frame at 1 Mbps that needs an ACK and one more fragment of 200 bytes. Remember the SIFS, the ACK air time, the next fragment's air time, and a slot of contention. Use the SIFS = 10 us and slot = 9 us defaults for 2.4 GHz.

## Key Terms

| Term                       | What people say                                                                                   | What it actually means                                                                                |
|----------------------------|---------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|
| MPDU                       | "A MAC protocol data unit."                                                                       | The bytes from Frame Control through FCS; the unit the radio transmits.                                |
| MSDU                       | "A MAC service data unit."                                                                        | The payload that LLC hands to the MAC; the unit fragmentation works on.                                |
| Frame Control              | "Two bytes of flags at the start of the header."                                                  | Eleven sub-fields packed into 16 bits in the exact order shown in Figure 4-29.                          |
| To DS / From DS            | "Two bits that say which way the frame is going."                                                 | A 2-bit selector that picks one of four address modes.                                                 |
| Duration                   | "A field that says how long the exchange is."                                                     | A 15-bit microsecond reservation loaded into every other station's NAV.                                 |
| NAV                        | "The network allocation vector."                                                                  | A per-station countdown that suppresses transmissions while the air is reserved.                       |
| BSSID                      | "The MAC of the AP, or a random address in an IBSS."                                             | The 48-bit identifier of the BSS; plays the role of Addr 3 in the To/From-DS modes.                    |
| DA / SA                    | "Destination and source addresses."                                                               | The 802 addresses of the final recipient and the original sender, end-to-end.                          |
| RA / TA                    | "Receiver and transmitter on the air."                                                            | The 802 addresses of the next-hop station on the radio, hop-by-hop.                                    |
| Sequence Control           | "16 bits of numbering."                                                                           | 4-bit fragment number concatenated with a 12-bit sequence number.                                      |
| More Fragments             | "A flag that says more is coming."                                                                | The bit that, together with the fragment number, lets the receiver reassemble an MSDU.                 |
| Protected Frame            | "A flag that says the body is encrypted."                                                         | Tells the receiver it has to decrypt before handing the body to LLC.                                   |
| FCS                        | "Frame check sequence."                                                                           | A 4-byte CRC-32 (polynomial 0x04C11DB7) covering everything from FC through the last body byte.        |
| IBSS                       | "Independent basic service set."                                                                  | An ad-hoc 802.11 network with no AP; To DS = From DS = 0.                                              |
| WDS                        | "Wireless distribution system."                                                                   | A bridge between two APs; To DS = From DS = 1 and Addr 4 carries the original SA.                      |

## Further Reading

- IEEE 802.11-2007, Section 7 — "Frame formats". The normative description of the MAC frame, including the exact bit positions in the Frame Control, the four address modes, and the Sequence Control layout.
- RFC 1042, "Standard for the transmission of IP datagrams over IEEE 802 networks". Defines the LLC/SNAP header that the 802.11 MAC places in front of an IP packet.
- Matthew S. Gast, "802.11 Wireless Networks: The Definitive Guide" (O'Reilly). The clearest walk-through of the four address modes, the NAV mechanism, and the way the Duration field ties the MAC layer to the physical layer.
