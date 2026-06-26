# Build an Ethernet Frame Parser That Distinguishes Ethernet II from 802.3

> The only reliable way to distinguish an Ethernet II frame from an IEEE 802.3 frame is to test the 2-byte field at offset 12: **≥ 1536 means EtherType (Ethernet II), ≤ 1500 means Length (IEEE 802.3)** — values in between are reserved and the frame must be discarded.

**Type:** Build
**Languages:** Python
**Prerequisites:** Ethernet MAC frame format and addressing (lesson 09), Python struct module basics
**Time:** ~75 minutes

## Learning Objectives

- Implement a parser that correctly classifies raw Ethernet frames as Ethernet II or IEEE 802.3 without misclassifying reserved values.
- Decode 802.1Q VLAN-tagged frames (EtherType 0x8100) by stripping the 4-byte tag and re-reading the inner EtherType.
- Extract and validate the FCS field, comparing a recomputed CRC-32 against the on-wire value.
- Handle LLC and LLC+SNAP sub-headers in IEEE 802.3 frames to recover the encapsulated protocol.
- Write a frame parser that produces a structured Python dict and passes a comprehensive test suite.

## The Problem

A security team is building an inline packet classifier that must route frames to different inspection pipelines based on Layer 3 protocol. The first implementation uses `struct.unpack('!H', frame[12:14])[0]` and routes on the result. This breaks in three real-world cases:

1. **Legacy NetWare IPX** traffic uses raw IEEE 802.3 frames with a Length value of 40–60. The classifier reads 40 as EtherType `0x0028` and finds no handler.
2. **Voice over IP** phones send 802.1Q-tagged frames (EtherType `0x8100` at offset 12). The real EtherType (0x0800 for SIP/RTP) sits at offset 16, but the classifier reads `0x8100` and routes incorrectly.
3. **STP BPDUs** arrive as 802.3 frames with DSAP=0x42 SSAP=0x42. The parser needs to read the LLC header to identify them.

Each failure is caused by the same root problem: the parser treats byte offset 12 as always containing a protocol identifier when it might be a length, a VLAN tag, or the start of a stack of tags.

## The Concept

### Parsing Decision Tree

```
frame[12:14] as uint16 → value V
│
├─ V == 0x8100 (or 0x88A8 for Q-in-Q)
│    └─ VLAN-tagged: skip 4 bytes, re-read new EtherType at offset 16
│         └─ may be another 0x8100 (double-tagged / QinQ)
│
├─ V >= 1536 (0x0600)
│    └─ Ethernet II: EtherType = V, payload starts at offset 14
│
├─ V <= 1500 (0x05DC)
│    └─ IEEE 802.3: Length = V, LLC header at offset 14
│         ├─ frame[14] DSAP, frame[15] SSAP, frame[16] Control
│         └─ if DSAP=0xAA, SSAP=0xAA → SNAP header at offset 17
│                 OUI (3 bytes) + Protocol (2 bytes) at offsets 17–21
│                 payload at offset 22
│
└─ 1501 <= V <= 1535
     └─ RESERVED: discard frame
```

### LLC and SNAP Sub-Headers

IEEE 802.3 frames use the 3-byte LLC (Logical Link Control) header:

```
Offset  Size  Field
    14     1  DSAP — Destination Service Access Point
    15     1  SSAP — Source Service Access Point
    16     1  Control (0x03 = UI unnumbered information)
    17+       Data
```

When DSAP = 0xAA and SSAP = 0xAA (the SNAP SAP), a 5-byte SNAP extension follows:

```
Offset  Size  Field
    17     3  OUI (Organization code; 0x000000 for EtherType namespace)
    20     2  Protocol ID (same values as EtherType when OUI=0x000000)
    22+       Actual payload
```

SNAP allows 802.3 frames to carry any EtherType protocol, bridging the two worlds.

**Common DSAP/SSAP values:**

| DSAP | SSAP | Protocol |
|------|------|---------|
| 0x42 | 0x42 | IEEE 802.1D STP/RSTP BPDUs |
| 0xAA | 0xAA | SNAP (sub-protocol in OUI+PID) |
| 0xFE | 0xFE | OSI IS-IS |
| 0xE0 | 0xE0 | Novell IPX |

## Build It

### Step 1: Core parser

```python
# eth_parser.py
import struct
import binascii
from dataclasses import dataclass, field
from typing import Optional

ETHERTYPE_8021Q   = 0x8100
ETHERTYPE_8021AD  = 0x88A8  # Q-in-Q outer tag
DSAP_SNAP         = 0xAA
DSAP_STP          = 0x42

ETHERTYPES = {
    0x0800: 'IPv4', 0x0806: 'ARP', 0x86DD: 'IPv6',
    0x8100: '802.1Q', 0x88CC: 'LLDP', 0x8847: 'MPLS',
    0x0600: 'XNS',
}

@dataclass
class ParsedFrame:
    dst_mac:    str
    src_mac:    str
    frame_type: str          # 'Ethernet II', 'IEEE 802.3', 'VLAN-tagged', 'RESERVED'
    ethertype:  Optional[int]   = None
    proto_name: Optional[str]   = None
    vlan_ids:   list            = field(default_factory=list)
    length:     Optional[int]   = None
    dsap:       Optional[int]   = None
    ssap:       Optional[int]   = None
    snap_oui:   Optional[bytes] = None
    snap_pid:   Optional[int]   = None
    payload:    bytes           = b''
    fcs_ok:     bool            = False
    errors:     list            = field(default_factory=list)


def _parse_mac(b: bytes) -> str:
    return ':'.join(f'{x:02X}' for x in b)


def _check_fcs(frame: bytes) -> bool:
    if len(frame) < 4:
        return False
    on_wire = struct.unpack('<I', frame[-4:])[0]
    computed = binascii.crc32(frame[:-4]) & 0xFFFFFFFF
    return on_wire == computed


def parse_frame(raw: bytes) -> ParsedFrame:
    """Parse a raw Ethernet frame (preamble stripped, FCS included)."""
    if len(raw) < 14:
        return ParsedFrame('', '', 'TRUNCATED',
                           errors=[f'Too short: {len(raw)} bytes'])

    result = ParsedFrame(
        dst_mac=_parse_mac(raw[0:6]),
        src_mac=_parse_mac(raw[6:12]),
        frame_type='unknown',
        fcs_ok=_check_fcs(raw),
    )

    offset = 12  # points to current EtherType/Length field

    # Unwrap VLAN tags
    while True:
        if offset + 2 > len(raw) - 4:
            result.errors.append('Truncated at EtherType/Length')
            result.frame_type = 'TRUNCATED'
            return result
        tl = struct.unpack('!H', raw[offset:offset+2])[0]
        if tl in (ETHERTYPE_8021Q, ETHERTYPE_8021AD):
            if offset + 4 > len(raw) - 4:
                result.errors.append('Truncated VLAN tag')
                break
            tci = struct.unpack('!H', raw[offset+2:offset+4])[0]
            vid = tci & 0x0FFF
            result.vlan_ids.append(vid)
            offset += 4  # skip TPID + TCI
        else:
            break

    tl = struct.unpack('!H', raw[offset:offset+2])[0]
    payload_start = offset + 2

    if result.vlan_ids:
        result.frame_type = 'VLAN-tagged'

    if 1501 <= tl <= 1535:
        result.frame_type = 'RESERVED'
        result.errors.append(f'Reserved EtherType/Length value: 0x{tl:04X}')
        return result

    if tl >= 1536:
        # Ethernet II
        if not result.vlan_ids:
            result.frame_type = 'Ethernet II'
        result.ethertype = tl
        result.proto_name = ETHERTYPES.get(tl, f'0x{tl:04X}')
        result.payload = raw[payload_start:-4]

    else:
        # IEEE 802.3 (tl <= 1500)
        if not result.vlan_ids:
            result.frame_type = 'IEEE 802.3'
        result.length = tl
        if payload_start + 3 > len(raw) - 4:
            result.errors.append('Truncated LLC header')
            return result
        result.dsap = raw[payload_start]
        result.ssap = raw[payload_start + 1]
        control    = raw[payload_start + 2]
        llc_data_start = payload_start + 3

        if result.dsap == DSAP_SNAP and result.ssap == DSAP_SNAP:
            # SNAP extension
            if llc_data_start + 5 > len(raw) - 4:
                result.errors.append('Truncated SNAP header')
                return result
            result.snap_oui = raw[llc_data_start:llc_data_start+3]
            result.snap_pid = struct.unpack('!H', raw[llc_data_start+3:llc_data_start+5])[0]
            if result.snap_oui == b'\x00\x00\x00':
                result.ethertype = result.snap_pid
                result.proto_name = ETHERTYPES.get(result.snap_pid, f'0x{result.snap_pid:04X}')
            result.payload = raw[llc_data_start+5 : payload_start + tl]
        else:
            result.payload = raw[llc_data_start : payload_start + tl]

    return result
```

### Step 2: Tests

```python
# test_eth_parser.py
import struct, binascii
from eth_parser import parse_frame, ParsedFrame

def make_fcs(data: bytes) -> bytes:
    return struct.pack('<I', binascii.crc32(data) & 0xFFFFFFFF)

def eth2_frame(dst, src, ethertype, payload):
    payload = payload.ljust(46, b'\x00')
    hdr = dst + src + struct.pack('!H', ethertype) + payload
    return hdr + make_fcs(hdr)

def eth803_frame(dst, src, dsap, ssap, data):
    llc = bytes([dsap, ssap, 0x03]) + data
    llc = llc.ljust(46, b'\x00')
    hdr = dst + src + struct.pack('!H', len(llc)) + llc
    return hdr + make_fcs(hdr)

BC  = bytes([0xFF]*6)
SRC = bytes([0x00,0x11,0x22,0x33,0x44,0x55])

def test_ethernet_ii():
    f = parse_frame(eth2_frame(BC, SRC, 0x0800, b'X'*20))
    assert f.frame_type == 'Ethernet II'
    assert f.ethertype == 0x0800
    assert f.proto_name == 'IPv4'
    assert f.fcs_ok

def test_ieee8023_stp():
    f = parse_frame(eth803_frame(BC, SRC, 0x42, 0x42, b'\x00'*10))
    assert f.frame_type == 'IEEE 802.3'
    assert f.dsap == 0x42
    assert f.ssap == 0x42

def test_reserved_range():
    raw = BC + SRC + struct.pack('!H', 0x05FF) + bytes(46)
    raw += make_fcs(raw)
    f = parse_frame(raw)
    assert f.frame_type == 'RESERVED'

def test_vlan_tagged():
    # 802.1Q: TPID=0x8100, TCI=0x0064 (VLAN 100), inner EtherType=0x0800
    inner = BC + SRC
    inner += struct.pack('!HH', 0x8100, 0x0064)   # tag
    inner += struct.pack('!H', 0x0800)             # inner EtherType
    inner += bytes(46) + make_fcs(inner + bytes(46))
    f = parse_frame(inner)
    assert f.vlan_ids == [100]
    assert f.ethertype == 0x0800

if __name__ == '__main__':
    for fn in [test_ethernet_ii, test_ieee8023_stp, test_reserved_range, test_vlan_tagged]:
        fn()
        print(f'{fn.__name__}: PASS')
```

Run with:
```
python3 test_eth_parser.py
```

Expected: all four tests print PASS.

## Use It

```python
# Quick pcap scan
import struct
from eth_parser import parse_frame

def scan_pcap(path):
    with open(path, 'rb') as f:
        f.read(24)
        while True:
            hdr = f.read(16)
            if len(hdr) < 16: break
            _, _, incl, _ = struct.unpack('<IIII', hdr)
            raw = f.read(incl)
            p = parse_frame(raw)
            tag = f' VLAN={p.vlan_ids}' if p.vlan_ids else ''
            print(f'{p.frame_type}{tag} {p.dst_mac} <- {p.src_mac} '
                  f'{p.proto_name or p.dsap} FCS={"OK" if p.fcs_ok else "BAD"}')

scan_pcap('capture.pcap')
```

## Ship It

```bash
# Run the test suite and save output
python3 test_eth_parser.py > outputs/parser-tests.txt

# Scan a real capture
python3 -c "from eth_parser import *; import struct
for raw in (f.read(16) and f.read(struct.unpack('<IIII',f.read(16))[2])
            for f in [open('capture.pcap','rb')] for _ in [f.read(24)]):
    p = parse_frame(raw)
    print(p.frame_type, p.proto_name or hex(p.dsap or 0))
"
```

## Exercises

1. **Double VLAN (QinQ):** Extend the parser to handle frames with both an outer 0x88A8 S-tag and an inner 0x8100 C-tag. Write a test with SVLAN=200, CVLAN=100, inner EtherType=0x86DD (IPv6). Verify `vlan_ids == [200, 100]` and `ethertype == 0x86DD`.

2. **SNAP IPX:** Novell NetWare sometimes uses SNAP encapsulation: DSAP=0xAA, SSAP=0xAA, OUI=`00:00:00`, PID=0x8137 (IPX). Construct such a frame and verify the parser extracts `snap_pid == 0x8137` and labels it correctly. Is the OUI significant here?

3. **Truncation robustness:** Feed the parser a 12-byte input (just dst+src, no EtherType), a 15-byte input (EtherType present but no payload), and a 13-byte input (1 byte of EtherType). Confirm that `errors` is non-empty for each and the parser does not raise an exception.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| EtherType | "protocol field at offset 12" | 16-bit value ≥ 1536 identifying the encapsulated Layer 3 protocol; defined in Ethernet II / DIX |
| LLC | "802.2 header" | Logical Link Control; 3-byte sub-header (DSAP, SSAP, Control) in IEEE 802.3 frames carrying the SAP identifiers |
| SNAP | "sub-protocol extension" | SubNetwork Access Protocol; 5-byte extension after LLC 0xAA/0xAA allowing EtherType protocols in 802.3 frames |
| DSAP | "destination SAP" | Destination Service Access Point; 1-byte LLC field identifying the upper-layer protocol at the receiver |
| 802.1Q | "VLAN tag" | IEEE standard for a 4-byte tag inserted between Src MAC and EtherType; carries 12-bit VLAN ID |
| TPID | "VLAN EtherType" | Tag Protocol Identifier; 0x8100 marks the start of an 802.1Q VLAN tag |
| QinQ | "double tagging" | Two nested VLAN tags; outer uses 0x88A8 (S-tag), inner uses 0x8100 (C-tag) |
| Reserved range | "illegal EtherType" | Values 1501–1535: undefined by any standard; frames bearing them must be discarded |

## Further Reading

- **IEEE 802.3-2022**, Clause 3.2.6 — Length/Type field disambiguation; authoritative source for the 1500/1536 boundary.
- **IEEE 802.2-1998** — LLC (Logical Link Control) standard; DSAP/SSAP registry and frame formats.
- **IEEE 802.1Q-2022** — Virtual LANs; TPID 0x8100, TCI structure, VLAN ID range.
- **RFC 1042** (1988) — IP over IEEE 802 using SNAP encapsulation; explains the DSAP=0xAA path.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Section 4.3.2 — Ethernet MAC sublayer and frame format.
