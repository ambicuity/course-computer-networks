# Reverse Engineer an Unknown Application Protocol

> You are handed a capture of traffic to an undocumented service on port 7331. No RFC, no documentation. Reconstruct the protocol's message format, state machine, and semantics from raw bytes alone.

**Type:** Capstone
**Languages:** Python, Wireshark, hex dumps
**Prerequisites:** Phase 12 application-protocol lessons; comfort with byte-order, struct packing, and TCP stream reassembly
**Time:** ~160 minutes

## Learning Objectives

- Reassemble a byte stream from ordered TCP segments and split it into application-level messages
- Infer the message framing structure (length-prefixed vs. delimiter-based vs. fixed-width) from byte patterns alone
- Classify message types by opcodes, tags, or magic bytes and build a type catalog
- Reconstruct the request-response state machine by correlating client and server messages with timing
- Detect optional fields, variable-length payloads, and compression or encoding layers
- Produce a protocol specification document sufficient for a third party to implement a compatible client

## The Problem

You join a legacy infrastructure team. A critical internal service listens on port 7331 and speaks a binary protocol nobody documented. The original author left five years ago. The monitoring dashboard shows the service handles a key-value store with get, put, delete, and list operations, plus a heartbeat and an error channel. Your job is to capture a representative session, reverse-engineer the wire format, and write a specification that a new client library can be built against.

The capture contains a mix of request-response exchanges and asynchronous server pushes. Some messages are fixed 8-byte headers followed by variable payloads. Others are length-prefixed. The protocol uses a mix of big-endian and little-endian fields, has a magic number for session initialization, includes a checksum on certain message types, and embeds a compressed payload for large values. You must discover all of this from the bytes.

This is the real-world skill of protocol archaeology. You do not get a spec. You get a trace. You must produce the spec.

## The Approach

Reverse-engineering a binary protocol is not guesswork — it is systematic reduction. You begin with a raw byte stream and progressively narrow the space of possible interpretations until only one consistent explanation remains. The seven stages below apply to any undocumented binary protocol, whether you are analyzing a game server, an industrial control system, or a legacy enterprise service.

**Stage 1: Stream Reassembly**

Open the capture in Wireshark, filter to `tcp.port == 7331`, and use "Follow TCP Stream" to export each direction as a raw byte sequence. Split the result into two files — one for bytes flowing client-to-server and one for bytes flowing server-to-client — because the two directions almost always use different message types and layouts. Label each byte range with the TCP sequence numbers it came from so you can correlate back to individual packets later.

**Stage 2: Framing Discovery**

Before you can interpret fields you must know where one message ends and the next begins. Scan the byte stream for repeating patterns at fixed offsets: a 2-byte or 4-byte value near the start of each message that equals the number of bytes that follow is a length-prefix frame; a constant byte sequence (0x0A, 0x00, 0xFF 0xFF) appearing repeatedly is a delimiter frame; identical total sizes for most messages suggests fixed-width framing. Run a sliding-window scan that tries every offset from 0 to 7 as a candidate length field, interpreting it as both big-endian and little-endian, and score each candidate by how consistently it predicts the start of the next apparent message boundary.

**Stage 3: Field Catalog**

Once you have reliable message boundaries, extract each message into a row of a spreadsheet or Python dict, indexed by message number. For each byte offset, compute the value across all messages: offsets that are constant across every message are invariants (magic bytes, version, protocol ID); offsets with low cardinality (2–10 distinct values) are enumerations (opcode, status, flags); offsets whose value matches the byte count of the remaining payload are length fields; offsets with high-entropy values near the end are likely checksums or sequence numbers. Build a running message-type table keyed by the opcode byte, with one row per observed opcode and columns for every field you have identified.

**Stage 4: State Machine Reconstruction**

Interleave the client and server streams, sorted by timestamp, to produce a unified event log. Look for request-response pairs: a client message at time T typically produces a server response within a few milliseconds. Tag each client message with the opcode of the server response that follows it. Messages that arrive from the server without a preceding client message are asynchronous pushes — heartbeat acknowledgements, server-initiated notifications, or error broadcasts. Draw a state diagram connecting the sequence: CONNECT → (magic exchange) → READY → (GET | PUT | DELETE | LIST)* → CLOSE, with an ERROR arc reachable from any state.

**Stage 5: Semantic Inference**

Match each opcode to the observable behavior visible in higher-level logs or monitoring. If the monitoring dashboard says the service is a key-value store, a client message followed by a server response that contains variable-length ASCII data is almost certainly a GET. A client message followed by a short fixed-length acknowledgement is likely a PUT or DELETE. Cross-reference key-length fields: if byte 8 of a request appears to encode a small integer (3, 5, 7) and the bytes immediately following that integer spell out recognizable ASCII strings, you have found the key field and confirmed the opcode's semantics. Build a table mapping each opcode to its inferred operation name, request field layout, and response field layout.

**Stage 6: Edge Case Discovery**

Once the happy path is mapped, look for messages that break the pattern. Search for response messages with an unusual high-bit opcode (e.g., 0xFF, 0x80) — these are typically error responses carrying an error code and a human-readable message string. Look for messages with a flags byte set to a non-zero value: flag bits commonly signal compression (zlib-deflated payload follows), continuation (this is a fragmented message), or encryption. Compare the entropy of payloads across messages of the same type: low entropy means structured data, high entropy means compressed or encrypted content. Find the boundary where entropy spikes and treat it as the start of the compressed region.

**Stage 7: Specification Writing**

Produce a machine-readable specification using BNF grammar notation. Write one production rule per message type, annotating each field with its byte width, byte order, and permitted values. Add a state machine diagram, an opcode table, and at least two annotated hex dumps — one happy-path exchange and one error exchange — so a reader can immediately ground the grammar in real bytes. Validate the specification by writing a minimal encoder in Python, generating a synthetic message, and checking that the framing, checksum, and length fields match what you found in the original trace.

## Build It

The target protocol uses this on-wire format for every message:

```
Offset  Size  Field           Notes
------  ----  -----           -----
0       4     magic           0xDEADBEEF, big-endian, constant on every message
4       1     opcode          message type (see opcode table below)
5       1     flags           bit 0 = compressed, bit 1 = response, bit 2 = error
6       2     payload_length  byte count of the payload field, big-endian
8       N     payload         opcode-specific content, N = payload_length
8+N     4     crc32           CRC-32 of bytes 0..(8+N-1), big-endian
```

Total minimum frame size: 12 bytes (header + zero-length payload + CRC).

**Step 1 — Recognize the magic.** Every message begins with the same four bytes. In a hex dump of the client stream you see:

```
0000  DE AD BE EF  01 00  00 04  03 66 6F 6F  3B 2A 1F 08
      [  magic  ]  op fl  [len]  [  payload ]  [  crc32 ]
```

The value `DE AD BE EF` at offset 0 appears at the start of every message. That is your sync point. Any position in the stream where these four bytes appear is a candidate message boundary.

**Step 2 — Identify the length prefix.** Bytes 6–7, interpreted as a big-endian unsigned short, equal `0x0004` = 4. Counting forward 4 bytes lands exactly on the next `DE AD BE EF` sequence. Repeat this check across 20 messages — it holds every time. Conclusion: bytes 6–7 are a 2-byte big-endian length field.

**Step 3 — Catalog the opcodes.** Byte 4 across the client stream takes these values and frequencies:

```
Opcode  Count  Inferred name
0x01    312    GET
0x02    188    PUT
0x03    47     DELETE
0x04    23     LIST
0x10    601    HEARTBEAT
0xFF    14     ERROR
```

The server response messages have bit 1 of the flags byte set (`flags & 0x02 == 1`), distinguishing responses from requests even when the opcode is the same value.

**Step 4 — Decode a GET exchange.** Client sends:

```
DE AD BE EF  01 00  00 04  03 66 6F 6F  3B 2A 1F 08
             ^GET   ^len=4  ^3 ^"foo"    ^crc32
```

Payload layout for GET request: 1-byte key length (0x03), followed by that many bytes of UTF-8 key (`66 6F 6F` = "foo").

Server responds within 2 ms:

```
DE AD BE EF  01 02  00 08  05 68 65 6C 6C 6F 00 00  A1 4C 3F 9D
             ^GET ^resp    ^5 ^"hello"  ^padding     ^crc32
```

Flags byte `0x02` means bit 1 (response) is set. Payload: 1-byte value length (0x05), followed by 5 bytes of value (`"hello"`), followed by 2 bytes of zero-padding to align the payload to a 4-byte boundary.

**Step 5 — Decode a PUT exchange.** Client sends:

```
DE AD BE EF  02 00  00 0B  03 66 6F 6F 05 77 6F 72 6C 64 00
             ^PUT   ^len=11 ^3 ^"foo"  ^5 ^"world"     ^pad
```

Payload layout for PUT: 1-byte key length + key bytes + 1-byte value length + value bytes + zero-padding to 4-byte alignment.

Server acknowledges with a fixed 4-byte payload:

```
DE AD BE EF  02 02  00 04  00 00 00 00  C3 5A 11 87
             ^PUT ^resp    ^status=OK   ^crc32
```

Status byte `0x00` = OK, `0x01` = key exists (update), `0x02` = quota exceeded.

**Step 6 — Spot the compressed flag.** One PUT in the trace has flags byte `0x01` (bit 0 set). The payload entropy spikes from ~3.2 bits/byte to ~7.8 bits/byte at offset 2 of the payload. Strip the first two bytes (key length + key), feed the rest to `zlib.decompress()`, and the result is valid UTF-8. Conclusion: when bit 0 of flags is set, the value portion of the payload is zlib-compressed.

**Step 7 — Verify the checksum.** The last 4 bytes of every message are a CRC-32 computed over all preceding bytes including the header. Compute `binascii.crc32(msg[:-4]) & 0xFFFFFFFF` for ten messages and compare to the last 4 bytes — they match every time. Any message with a mismatched CRC in the trace is a retransmission artifact; the server sends an ERROR response with opcode `0xFF` and error code `0x03` (checksum mismatch).

**Step 8 — Reconstruct the state machine.** Every session begins with a HEARTBEAT (opcode `0x10`) from the client carrying a 4-byte Unix timestamp as payload. The server echoes it back with the response flag set. After that exchange the session enters READY state and accepts GET/PUT/DELETE/LIST messages in any order. The session ends when the TCP connection closes — there is no explicit CLOSE message. ERROR messages (`0xFF`) can arrive at any time and do not terminate the session unless the error code is `0x01` (fatal protocol error).

## Use It

| Task | Tool | Evidence |
|------|------|----------|
| Export raw TCP payload bytes per direction | Wireshark: File > Export Objects > follow stream, select "Raw" | Two binary files, one per direction, with no IP/TCP headers |
| Scan for length-prefix candidates | Python `struct.unpack(">H", stream[i:i+2])` at every offset 0–7 | Candidate scores: offset 6 big-endian scores 0.97, all others < 0.3 |
| Compute per-offset entropy across all messages | `scipy.stats.entropy` over byte frequency at each offset | Offsets 0–7 low entropy (header), offsets 8+ high entropy (payload) |
| Identify opcode distribution | Group by `msg[4]`, count occurrences | Table of 6 distinct opcodes with counts confirming GET dominates |
| Validate CRC field | `binascii.crc32(msg[:-4]) & 0xFFFFFFFF == struct.unpack(">I", msg[-4:])[0]` | 100% match across all 1185 messages in the trace |
| Detect compressed payloads | Check `msg[5] & 0x01`; attempt `zlib.decompress(payload[key_end:])` | 7 PUT messages carry compressed values; all decompress cleanly |

## Ship It

**Protocol specification (BNF)**

```
message      ::= magic opcode flags length payload crc32
magic        ::= %xDE %xAD %xBE %xEF
opcode       ::= %x01 / %x02 / %x03 / %x04 / %x10 / %xFF
flags        ::= OCTET                ; bit0=compressed, bit1=response, bit2=error
length       ::= UINT16BE             ; byte count of payload field
payload      ::= get-req / put-req / del-req / list-req
               / get-resp / put-resp / del-resp / list-resp
               / heartbeat / error-msg
crc32        ::= UINT32BE             ; CRC-32 of bytes [0, 8+N)

get-req      ::= key-len key
put-req      ::= key-len key val-len value *%x00   ; padded to 4-byte boundary
del-req      ::= key-len key
list-req     ::= prefix-len prefix
get-resp     ::= val-len value *%x00
put-resp     ::= status
del-resp     ::= status
list-resp    ::= entry-count *(key-len key)
heartbeat    ::= UINT32BE             ; Unix timestamp
error-msg    ::= error-code msg-len message

key-len      ::= OCTET
val-len      ::= OCTET
prefix-len   ::= OCTET
entry-count  ::= UINT16BE
msg-len      ::= OCTET
status       ::= %x00 / %x01 / %x02  ; OK / updated / quota
error-code   ::= %x01 / %x02 / %x03  ; fatal / not-found / bad-crc
```

**Deliverables checklist**

- `outputs/protocol-spec.md` — BNF grammar, opcode table, field layout tables with byte-order annotations, and two annotated hex dumps (happy-path GET and ERROR response)
- `outputs/opcode-table.txt` — opcode value, name, request payload layout, response payload layout, observed frequency
- `outputs/decoder.py` — Python script that reads the raw capture export, parses every message using the reconstructed spec, and prints a human-readable transcript
- `outputs/dissector.lua` — Wireshark Lua dissector stub that registers on port 7331 and labels the magic, opcode, flags, length, payload, and CRC fields in the packet detail pane
- `outputs/state-machine.txt` — state diagram in text form: states, transitions, trigger opcodes, and timing constraints observed in the trace

## Exercises

1. **Implement the CRC validator.** Write a Python function `verify_message(raw: bytes) -> bool` that returns `True` if and only if the last 4 bytes match the CRC-32 of the preceding bytes. Run it against every message in the trace and report what fraction pass. For those that fail, examine whether they cluster around a particular opcode or timestamp — this tells you whether corruption is systematic or random.

2. **Write a Wireshark Lua dissector.** Create `dissector.lua` that calls `DissectorTable.get("tcp.port"):add(7331, proto)` and uses `buffer(0,4):uint()` to verify the magic, then labels each field in the tree. Test it by loading the capture and confirming that the packet detail pane shows "Magic: 0xDEADBEEF", "Opcode: GET (0x01)", "Payload Length: 4", and "CRC32: 0x3B2A1F08" for the first client message. A working dissector turns raw bytes into named fields, which makes finding anomalies dramatically faster.

3. **Fuzz the length field.** Write a fuzzer that generates syntactically valid messages but sets the `payload_length` field to values that do not match the actual payload size: zero, `0xFFFF`, `payload_length + 1`, and `payload_length - 1`. Send each variant to a local test server and record whether it disconnects, sends an ERROR response, or silently accepts the malformed message. Document what error code (if any) the server returns for each case — this reveals how robust the server's parser is.

4. **Detect protocol version changes.** You receive two captures separated by six months. Write a script that compares the opcode tables and field layouts extracted from each. Specifically: (a) identify any opcodes present in one trace but not the other, (b) check whether the payload length distribution for shared opcodes has changed, and (c) check whether the magic number is identical. Differences in (b) without differences in (c) suggest a field was added or removed within a backwards-compatible version; differences in (c) indicate a protocol break.

5. **Handle TLV payloads.** Modify the decoder to handle a hypothetical variant where the payload uses Type-Length-Value encoding: each field in the payload is prefixed by a 1-byte type tag and a 1-byte length, followed by that many bytes of value. Rewrite the `get-resp` parser so that it iterates over TLV fields rather than assuming fixed offsets. Explain how this changes the framing-discovery algorithm: with TLV you no longer need to know field positions in advance, but you do need to trust that type tags are consistent across messages.

6. **Detect and decompress compressed values.** Extend `decoder.py` to check `flags & 0x01` on every message. When the flag is set, extract the value portion of the payload (after the key bytes), call `zlib.decompress()` on it, and replace the raw bytes with the decompressed string in the transcript output. Add error handling for the case where decompression fails — this can happen if the compression flag is set incorrectly or if the capture contains a partial message. Log the original compressed size and the decompressed size for each such message.

7. **Reconstruct a session from fragments.** Take the capture and artificially split it at a message boundary by truncating the byte stream mid-message. Write a reassembler that buffers incoming bytes, waits until it has at least 8 bytes (the header), reads `payload_length` from bytes 6–7, then waits until it has `8 + payload_length + 4` bytes before attempting to parse. Confirm that the reassembler correctly handles the case where a TCP segment boundary falls inside the magic bytes, inside the length field, or inside the CRC field.

## Key Terms

| Term | Definition |
|------|------------|
| Magic number | A fixed multi-byte constant at a known offset in every message that identifies the protocol and validates that the parser is synchronized to a message boundary. The value `0xDEADBEEF` is a magic number. |
| Opcode | A single byte (or short integer) at a fixed header offset that classifies the message type. Opcodes are the primary key for building a message-type catalog during reverse engineering. |
| Length-prefix framing | A framing strategy where a fixed-size integer field immediately preceding the variable payload encodes how many bytes the payload contains. The parser reads exactly that many bytes before expecting the next frame. |
| Little-endian | A byte-order convention where the least-significant byte of a multi-byte integer is stored at the lowest memory address. Intel x86 processors are natively little-endian; many network protocols use big-endian (network byte order) instead. |
| Big-endian | A byte-order convention where the most-significant byte of a multi-byte integer is stored at the lowest memory address. Also called network byte order. Python's `struct.pack(">H", n)` produces a big-endian unsigned short. |
| TLV (Type-Length-Value) | A self-describing encoding where each field is prefixed by a type tag and a length, so the parser does not need prior knowledge of field positions or counts. ASN.1 BER and many extension protocols use TLV. |
| BNF grammar | Backus-Naur Form — a formal notation for describing the syntax of a protocol or language as a set of production rules. A BNF grammar for a binary protocol lists each message type as a sequence of named fields with their sizes and permitted values. |
| Dissector | A Wireshark plugin (written in C or Lua) that decodes a specific protocol and labels its fields in the packet detail pane. Writing a dissector is one of the fastest ways to validate a reconstructed protocol specification against a real capture. |
| State machine | A model of a protocol session as a set of named states (CONNECT, READY, ERROR, CLOSED) and transitions between them triggered by specific message types. The state machine defines which messages are legal at each point in the session. |
| Checksum | A fixed-size integer derived from the message bytes and appended to the message so the receiver can detect corruption. CRC-32 is a common 4-byte checksum used in Ethernet frames, ZIP files, and many application protocols. |
| Protocol archaeology | The practice of reconstructing an undocumented protocol specification solely from packet captures, binary analysis, and behavioral observation — without access to source code or documentation. The output is a specification document that enables a third party to build a compatible implementation. |

## Further Reading

- "Attacking Network Protocols" by James Forshaw (No Starch Press, 2017) — Chapter 4 covers binary protocol reverse engineering with worked examples; Chapter 5 covers fuzzing undocumented protocols.
- Wireshark Developer's Guide, "Writing a Dissector" — official documentation for writing Lua and C dissectors; covers `proto.fields`, `DissectorTable`, and the `tvbuff` API used to slice message bytes. Available at https://www.wireshark.org/docs/wsdg_html/.
- RFC 4506, "XDR: External Data Representation Standard" — a reference binary encoding specification useful for comparison when studying what a well-documented binary protocol looks like.
- "The Scapy Documentation" — Scapy's `Packet` class and field descriptors (`ByteField`, `ShortField`, `StrLenField`) let you define a binary protocol structure in Python and both parse and craft messages with the same class definition. https://scapy.readthedocs.io/.
- "Reverse Engineering of Binary Protocols" by Dunlap et al. (IEEE S&P 2012) — a surveyed taxonomy of automated protocol reverse-engineering techniques including format inference, state-machine extraction, and semantic labeling; useful for understanding where manual analysis ends and automated tooling begins.
