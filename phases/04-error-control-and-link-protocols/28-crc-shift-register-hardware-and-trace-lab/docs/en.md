# CRC Shift-Register Hardware and Live Packet-Trace Lab

> A CRC is not computed by long division at run time — it is computed by a **linear feedback shift register (LFSR)** that processes one bit per clock cycle and accumulates the remainder in hardware registers, making CRC-32 feasible at wire speed for any link rate from 10 Mbps to 400 Gbps.

**Type:** Lab
**Languages:** Python, Wireshark, packet traces
**Prerequisites:** Polynomial arithmetic mod 2, IEEE 802.3 frame format (preamble, FCS field), basic Python
**Time:** ~75 minutes

## Learning Objectives

- Describe the LFSR circuit that computes CRC-32 in hardware and trace one complete byte through it by hand.
- Implement a software CRC-32 engine two ways — bit-serial LFSR simulation and table-driven — and verify they produce identical results.
- Explain why the IEEE 802.3 CRC-32 uses a reflected (bit-reversed) convention and what "pre-conditioning" and "post-conditioning" mean.
- Extract raw FCS bytes from a pcap file and verify them against a Python recomputation.
- Identify the three error classes that CRC-32 guarantees to detect and state the residue value a correct frame must produce.

## The Problem

Your team has inherited a network appliance that strips the 4-byte FCS from forwarded Ethernet frames before retransmitting them. The vendor's documentation says "CRC is re-generated on egress," but you have started seeing silent data corruption: a tcpdump at the far end shows frames arriving with valid FCS values that do not match the payload. The appliance is recomputing CRC over the wrong byte range — it starts after the preamble but includes the padding bytes that should be excluded.

To file a coherent bug report you need to:
1. Know exactly which bytes the IEEE 802.3 CRC-32 covers.
2. Be able to recompute the FCS for any captured frame independently.
3. Understand the bit-ordering convention so your result matches Wireshark's "Frame Check Sequence" field byte for byte.

This requires understanding the CRC not just as a mathematical formula but as the specific hardware circuit that the 802.3 standard defines.

## The Concept

### CRC as Polynomial Division — Quick Recap

A CRC with generator polynomial G(x) of degree r appends r zero bits to message M(x), divides x^r·M(x) by G(x) modulo 2, and appends the r-bit remainder. The receiver divides the received frame (including FCS) by G(x); if the result is zero, no error was detected.

The IEEE 802.3 generator polynomial (CRC-32) is:

```
G(x) = x^32 + x^26 + x^23 + x^22 + x^16 + x^12 + x^11 + x^10
            + x^8  + x^7  + x^5  + x^4  + x^2  + x   + 1
```

In hex, the 32 coefficients below x^32 are `0x04C11DB7`.

### The LFSR Circuit

Long division over GF(2) maps directly to a shift register with XOR feedback taps. For a degree-r polynomial, the hardware is:

```
Input bit ──►[XOR]──►[b0]──►[b1]──► ... ──►[b31]
               ▲                              │
               └──────── feedback taps ───────┘
                         (positions matching G(x))
```

Each clock cycle:
1. Shift all register bits one position to the right.
2. XOR the shifted-out bit (b31) with the incoming data bit to produce a feedback bit.
3. XOR the feedback bit into register positions that correspond to the 1-coefficients of G(x).

After processing all message bits (with the appended r zeros), the register holds the CRC remainder.

**Concrete example — tracing one bit through CRC-32:**

Initial state (all ones, per 802.3 pre-conditioning): `0xFFFFFFFF`

Incoming bit = 1 (first data bit after 802.3 pre-conditioning):
```
feedback = bit31_of_register XOR incoming_bit
         = 1 XOR 1 = 0
register = (register << 1) with XOR feedback at tap positions
```

Processing 32 bits of zeros at the end implements "shift out the remainder."

### IEEE 802.3 CRC-32 Conventions

The 802.3 standard specifies four important deviations from bare polynomial division:

| Convention | What it means | Why |
|------------|--------------|-----|
| Pre-conditioning | Initialize register to `0xFFFFFFFF` (all ones) | Detects leading zeros prepended to a frame |
| Bit reversal (reflected) | Process LSB of each byte first | Matches the serial bit order on the wire |
| Post-conditioning | Invert all 32 register bits before appending | Detects trailing zeros appended to a frame |
| Residue check | Correct frames produce remainder `0xC704DD7B` | Receiver checks for this magic constant |

**Bytes covered by FCS:** The CRC covers the frame from Destination MAC address through the end of the Data/Pad field. It does NOT cover the preamble (8 bytes) or the FCS field itself.

```
Preamble  Dst MAC  Src MAC  Type/Len  Data+Pad  FCS
8 bytes   6 bytes  6 bytes  2 bytes   46-1500B  4 bytes
│         │                           │         │
│         └───── CRC-32 covers ───────┘         │
│  (not covered)                      (not covered)
```

### Table-Driven CRC: The Software Optimization

The bit-serial LFSR processes 1 bit per iteration — 8 iterations per byte. A table-driven approach precomputes the CRC effect of all 256 possible byte values:

```python
def _make_table():
    table = []
    for byte in range(256):
        crc = byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320  # reflected polynomial
            else:
                crc >>= 1
        table.append(crc)
    return table
```

`0xEDB88320` is `0x04C11DB7` with its bits reversed (reflected), matching the LSB-first convention.

Processing one byte then becomes:

```python
crc = table[(crc ^ byte) & 0xFF] ^ (crc >> 8)
```

One table lookup per byte instead of 8 XOR-shift operations. Modern NICs use 64-bit or SIMD variants that process 8+ bytes per cycle.

### Error Detection Guarantees

For any frame up to 2^32 − 1 bits, CRC-32 with the 802.3 polynomial guarantees detection of:

| Error type | Guarantee |
|-----------|-----------|
| All single-bit errors | 100% detected |
| All double-bit errors | 100% detected |
| All odd-number-of-bit errors | 100% detected (x+1 is a factor of G(x)) |
| All burst errors ≤ 32 bits | 100% detected |
| Burst errors of length 33 | All except 1 in 2^31 ≈ 1 in 2 billion |
| Longer bursts | All except 1 in 2^32 |

For a typical Ethernet frame, the probability of an undetected error is approximately 1 in 4.3 × 10^9.

### Reading FCS in Wireshark

Wireshark hides the FCS by default (it is stripped by most drivers). To see it:

1. Edit → Preferences → Protocols → Ethernet → uncheck "Assume packets have FCS"
   (or check "Always add Ethernet FCS" depending on version)
2. Alternatively, capture with `tcpdump -i eth0 -w out.pcap` and verify the interface passes FCS through (most Linux raw sockets do not).

The 4 FCS bytes appear in little-endian order on the wire: the CRC value `0x12345678` is transmitted as bytes `78 56 34 12`.

## Build It

### Step 1: Bit-serial LFSR simulation

```python
# crc_lfsr.py
POLY = 0x04C11DB7  # IEEE 802.3 CRC-32 polynomial (non-reflected)

def crc32_lfsr(data: bytes) -> int:
    """Compute CRC-32 bit-serially, MSB-first, without reflection."""
    register = 0xFFFFFFFF  # pre-conditioning
    for byte in data:
        for bit_pos in range(7, -1, -1):  # MSB first
            bit = (byte >> bit_pos) & 1
            feedback = ((register >> 31) ^ bit) & 1
            register = (register << 1) & 0xFFFFFFFF
            if feedback:
                register ^= POLY
    return register ^ 0xFFFFFFFF  # post-conditioning
```

### Step 2: Table-driven (reflected) implementation matching 802.3 wire order

```python
# crc32_table.py
import struct

def _make_crc_table():
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ 0xEDB88320 if crc & 1 else crc >> 1
        table.append(crc)
    return table

_TABLE = _make_crc_table()

def crc32_802_3(data: bytes) -> int:
    """CRC-32 matching IEEE 802.3: reflected, pre/post-conditioned."""
    crc = 0xFFFFFFFF
    for byte in data:
        crc = _TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF

def verify_frame(frame_with_fcs: bytes) -> bool:
    """Return True if the frame (including 4-byte FCS) has correct CRC."""
    RESIDUE = 0xC704DD7B
    crc = 0xFFFFFFFF
    for byte in frame_with_fcs:
        crc = _TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return (crc ^ 0xFFFFFFFF) == RESIDUE

def fcs_bytes(data: bytes) -> bytes:
    """Return the 4 FCS bytes to append (little-endian, matching wire order)."""
    return struct.pack('<I', crc32_802_3(data))
```

### Step 3: Verify against Python's built-in

```python
import binascii
from crc32_table import crc32_802_3, fcs_bytes

# Test frame: Dst=FF:FF:FF:FF:FF:FF Src=00:11:22:33:44:55 Type=0x0800 + 46-byte payload
dst = bytes([0xFF]*6)
src = bytes([0x00, 0x11, 0x22, 0x33, 0x44, 0x55])
ethertype = bytes([0x08, 0x00])
payload = b'Hello, Ethernet!' + bytes(30)  # pad to 46 bytes
frame = dst + src + ethertype + payload

ours = crc32_802_3(frame)
stdlib = binascii.crc32(frame) & 0xFFFFFFFF
print(f"Our CRC-32:    0x{ours:08X}")
print(f"binascii CRC:  0x{stdlib:08X}")
print(f"Match: {ours == stdlib}")
print(f"FCS bytes (wire order): {fcs_bytes(frame).hex()}")
```

Run with:
```
python3 crc32_table.py && python3 verify.py
```

Expected: both CRC values match, and `Match: True`.

### Step 4: Parse a pcap and verify FCS

```python
# verify_pcap.py  — reads a raw Ethernet pcap (linktype 1)
import struct, sys
from crc32_table import crc32_802_3

def read_pcap_frames(path):
    with open(path, 'rb') as f:
        magic, ver_maj, ver_min, _, _, snaplen, link = struct.unpack('<IHHiIII', f.read(24))
        assert link == 1, f"Expected Ethernet linktype 1, got {link}"
        while True:
            hdr = f.read(16)
            if len(hdr) < 16:
                break
            ts_sec, ts_usec, incl_len, orig_len = struct.unpack('<IIII', hdr)
            yield f.read(incl_len)

if __name__ == '__main__':
    path = sys.argv[1]
    ok = err = 0
    for frame in read_pcap_frames(path):
        if len(frame) < 64:
            continue  # too short to have FCS
        payload = frame[:-4]
        fcs_in_frame = struct.unpack('<I', frame[-4:])[0]
        computed = crc32_802_3(payload)
        if computed == fcs_in_frame:
            ok += 1
        else:
            err += 1
            print(f"FCS MISMATCH: got 0x{fcs_in_frame:08X}, expected 0x{computed:08X}")
    print(f"Frames checked: {ok+err}  OK: {ok}  BAD: {err}")
```

## Use It

| Task | Command | What to look for |
|------|---------|-----------------|
| Verify CRC implementation | `python3 verify.py` | "Match: True" and correct FCS hex |
| Check a pcap for FCS errors | `python3 verify_pcap.py capture.pcap` | "BAD: 0" on a clean capture |
| Inspect FCS in Wireshark | Enable FCS display in Preferences | 4 bytes at frame end labeled "Frame check sequence" |
| Trace single byte manually | Paper exercise with LFSR table | Register state matches crc32_lfsr output |
| Identify which bytes are covered | `python3 verify.py` — modify to exclude first 6 bytes | CRC changes, confirming dst MAC is included |

## Ship It

Save the verifier as a reusable capture-QA tool:

```bash
# Capture 100 frames including FCS (requires a capture interface that passes FCS)
sudo tcpdump -i eth0 -c 100 --snapshot-length=1522 -w /tmp/test.pcap

# Verify all FCS values
python3 verify_pcap.py /tmp/test.pcap

# Expected on a healthy link: "Frames checked: 100  OK: 100  BAD: 0"
```

The `crc32_802_3()` function is a drop-in diagnostic tool: call it on any `bytes` object that represents an Ethernet frame from Dst MAC through the last data byte, then compare against the captured FCS.

## Exercises

1. **LFSR trace:** Manually trace the bit-serial LFSR for the 8-bit message `0xAB` (10101011) using the 4-bit generator `x^4 + x + 1` (binary: `10011`). Initialize to `0xF`. Show register state after each of the 8 input bits plus 4 zero-pad bits. What is the 4-bit CRC remainder?

2. **Residue verification:** Take a correctly CRC'd 64-byte Ethernet frame (Dst+Src+Type+Data+FCS). Feed all 68 bytes — including the 4 FCS bytes — through `crc32_802_3()`. Confirm the result equals `0xC704DD7B`. Then flip one bit in the payload and confirm the residue changes. What is the new residue?

3. **Coverage boundary:** Modify `verify.py` to compute CRC over (a) just the payload without Dst MAC, and (b) the entire frame including FCS. Explain why both give wrong results compared to the correct computation, and what bug each variant corresponds to in a real appliance.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| LFSR | "shift register CRC" | Linear Feedback Shift Register; hardware circuit that computes CRC one bit per clock cycle using XOR taps |
| FCS | "the CRC field" | Frame Check Sequence; the 4-byte CRC-32 appended to every Ethernet frame |
| Pre-conditioning | "seeding with ones" | Initializing the LFSR to all-ones (0xFFFFFFFF) before processing; detects frames with leading zero bits prepended |
| Post-conditioning | "inverting the result" | XOR the final LFSR state with 0xFFFFFFFF; detects frames with trailing zeros appended |
| Reflected polynomial | "LSB-first CRC" | Bit-reversed form of G(x) — 0xEDB88320 instead of 0x04C11DB7; matches the serial bit order on the Ethernet wire |
| Residue | "magic constant check" | Value 0xC704DD7B that a correct frame (data + FCS) must produce when run through the CRC engine at the receiver |
| CRC-32 generator | "0x04C11DB7" | The 32 lower-order coefficients of the IEEE 802.3 polynomial; the degree-32 leading coefficient is implicit |
| Table-driven CRC | "byte-at-a-time CRC" | Precomputed 256-entry table that folds 8 bit-serial steps into one lookup; standard software optimization |

## Further Reading

- **IEEE 802.3-2022**, Section 3.2.9 — Normative definition of CRC-32, including pre/post-conditioning, bit ordering, and the residue test.
- Peterson, W. W. and Brown, D. T., "Cyclic Codes for Error Detection," *Proceedings of the IRE*, vol. 49, 1961 — Original paper showing that polynomial codes are computable by shift register circuits.
- Williams, R., "A Painless Guide to CRC Error Detection Algorithms," 1993 — Comprehensive treatment of all CRC conventions (reflection, initialization, final XOR); available at https://www.zlib.net/crc_v3.txt
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Section 3.2.2 — Polynomial code derivation and error-detection properties.
- **RFC 3385** — Notes on CRC-32 usage in Internet protocols and the exact byte-order convention used on the wire.
