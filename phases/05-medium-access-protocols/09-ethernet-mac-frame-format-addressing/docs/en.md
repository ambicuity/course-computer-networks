# Ethernet MAC Frame Format, 48-Bit Addressing, and the Type-vs-Length Field

> The single most important disambiguation in Ethernet is the **Type/Length field at byte offset 12**: a value ≥ 1536 (0x0600) is an EtherType identifying the Layer 3 protocol (Ethernet II / DIX), while a value ≤ 1500 is an IEEE 802.3 length field — and every Ethernet implementation since 1997 must handle both conventions simultaneously.

**Type:** Learn
**Languages:** Python, packet traces
**Prerequisites:** Classic Ethernet physical layer (preamble, Manchester encoding), CRC-32 / FCS field
**Time:** ~75 minutes

## Learning Objectives

- Recite the exact byte layout and field sizes of an Ethernet II (DIX) frame and an IEEE 802.3 frame and identify the one field that distinguishes them.
- Decode a 48-bit MAC address, identify the I/G (Individual/Group) and U/L (Universally/Locally administered) bits, and construct broadcast and multicast addresses.
- Explain why the minimum frame length is 64 bytes and calculate the minimum data payload (46 bytes) accounting for all fixed header fields.
- Trace what happens on the wire when a payload is shorter than 46 bytes (PAD insertion) and how the receiver determines where the real data ends.
- Map EtherType values to protocols: 0x0800 (IPv4), 0x0806 (ARP), 0x86DD (IPv6), 0x8100 (VLAN/802.1Q).
- Explain the role of the OUI in a MAC address and how IEEE RA assigns 24-bit OUIs to vendors.

## The Problem

A packet analyzer written by a junior engineer parses incoming frames by reading the 2-byte field at offset 12 as an EtherType unconditionally. The analyzer works fine for most traffic but crashes on raw 802.3 frames from a legacy NetWare IPX node: those frames have a Length value of 60 (the actual payload size), but the analyzer interprets 60 as EtherType 0x003C, finds no handler, and throws an unhandled exception.

A second bug surfaces on broadcast ARP probes: the code that extracts the source MAC address reads 6 bytes starting at byte offset 6 but for a specific VoIP device it gets a different address each time because the VoIP phone uses locally administered MAC addresses (the U/L bit = 1) that change on reboot. The engineer did not know U/L-administered addresses existed.

Both bugs stem from not reading the IEEE 802.3 frame specification carefully. Understanding the frame format precisely eliminates them.

## The Concept

### Frame Layout: Ethernet II vs IEEE 802.3

Both formats share the same preamble, MAC addresses, and FCS. The difference is at byte offset 12:

```
Ethernet II (DIX) frame — on-wire layout after preamble stripped:
 Offset  Size   Field
      0     6   Destination MAC address
      6     6   Source MAC address
     12     2   EtherType (≥ 0x0600 = 1536)
     14   46–1500  Payload (no length field — determined by EtherType protocol)
   last     4   FCS (CRC-32)

IEEE 802.3 frame — on-wire layout after preamble stripped:
 Offset  Size   Field
      0     6   Destination MAC address
      6     6   Source MAC address
     12     2   Length (≤ 0x05DC = 1500): byte count of LLC Data field
     14     1   DSAP  (LLC Destination Service Access Point)
     15     1   SSAP  (LLC Source Service Access Point)
     16     1   Control
     17  variable  LLC Data (original 802.3; today often SNAP follows)
   last     4   FCS (CRC-32)
```

**The disambiguation rule (IEEE 802.3-2022, clause 3.2.6):**

| Field value at offset 12 | Interpretation |
|--------------------------|---------------|
| 0x0000 – 0x05DC (0–1500) | IEEE 802.3 Length — number of bytes of LLC data |
| 0x0600 – 0xFFFF (1536–65535) | Ethernet II EtherType — Layer 3 protocol ID |
| 0x05DD – 0x05FF (1501–1535) | Undefined / reserved; discard frame |

The gap between 1500 and 1536 exists deliberately so there is no ambiguity. The Ethernet II EtherType space starts well above the maximum valid 802.3 length.

### Field-by-Field Reference

**Preamble (8 bytes, stripped before MAC layer sees the frame):**

```
Bytes 1–7:  0xAA 0xAA 0xAA 0xAA 0xAA 0xAA 0xAA  (10101010 × 7)
Byte  8:    0xAB                                  (10101011 — SFD)
```

**Destination MAC (6 bytes, offset 0):**
- Bit 0 of byte 0 (first bit transmitted) = I/G bit: 0 = unicast, 1 = group (multicast or broadcast)
- Bit 1 of byte 0 = U/L bit: 0 = universally administered (OUI-assigned), 1 = locally administered

```
Broadcast:  FF:FF:FF:FF:FF:FF  (all ones — received by everyone)
IPv4 mcast: 01:00:5E:xx:xx:xx  (I/G=1, low 23 bits of multicast IP group)
IPv6 mcast: 33:33:xx:xx:xx:xx  (I/G=1, low 32 bits of IPv6 multicast address)
```

**Source MAC (6 bytes, offset 6):**
- Always unicast (I/G bit = 0)
- U/L = 0: assigned by IEEE RA via 24-bit OUI (Organizationally Unique Identifier)
- U/L = 1: locally administered — often used for VMs, VPN tunnels, bonded interfaces

**OUI structure:**
```
MAC:  AA:BB:CC:DD:EE:FF
      ├────────┤ ├────────┤
       OUI (3B)   NIC-specific (3B)
       assigned    assigned by
       by IEEE RA  vendor
```

Example: `00:1A:2B:xx:xx:xx` — OUI `00:1A:2B` registered to a specific vendor.

**EtherType / Length (2 bytes, offset 12):**

| Value | Protocol |
|-------|---------|
| 0x0800 | IPv4 |
| 0x0806 | ARP |
| 0x86DD | IPv6 |
| 0x8100 | IEEE 802.1Q VLAN tag (4 extra bytes follow before the real EtherType) |
| 0x88CC | LLDP (Link Layer Discovery Protocol) |
| 0x8847 | MPLS unicast |
| 0x0600 | XNS (Xerox; first Ethernet II EtherType) |

**Data + Pad (46–1500 bytes):**
- Minimum 46 bytes: required to ensure the frame on the wire is at least 64 bytes (6+6+2+46+4 = 64), satisfying CSMA/CD slot time.
- If actual data < 46 bytes, the sender NIC appends **PAD** bytes (value 0x00 or unspecified) to reach 46.
- The receiver uses the EtherType (Ethernet II) or LLC Length (802.3) to find the real data end; PAD bytes are invisible to the network layer.
- Maximum 1500 bytes: the standard Ethernet MTU. Jumbo frames (up to 9000 bytes) require explicit NIC and switch configuration and are non-standard.

**FCS (4 bytes, last):**
- CRC-32 over Dst MAC through end of Data+Pad (not preamble, not FCS itself).
- Transmitted LSB-first (little-endian).
- Correct frame produces residue `0xC704DD7B` at receiver.

### 802.1Q VLAN Tagging

When a frame carries a VLAN tag, 4 bytes are inserted between the Source MAC and the EtherType:

```
 Offset  Size   Field
      0     6   Destination MAC
      6     6   Source MAC
     12     2   0x8100 (TPID — Tag Protocol Identifier)
     14     2   TCI: PCP(3b) DEI(1b) VID(12b)
     16     2   Inner EtherType (the real Layer 3 protocol)
     18  46–1500  Payload
   last     4   FCS
```

The 12-bit VID (VLAN Identifier) supports VLANs 1–4094 (0 and 4095 are reserved).

### Frame Size Constraints

| Constraint | Value | Source |
|-----------|-------|--------|
| Minimum frame (wire) | 64 bytes | CSMA/CD slot time at 10 Mbps |
| Maximum frame (wire) | 1518 bytes | IEEE 802.3 (without VLAN tag) |
| Maximum frame with 802.1Q | 1522 bytes | IEEE 802.3ac amendment |
| Jumbo frame (non-standard) | up to 9018 bytes | Vendor convention |
| Minimum payload | 46 bytes | 64 − 6 − 6 − 2 − 4 = 46 |
| Maximum payload (MTU) | 1500 bytes | 1518 − 6 − 6 − 2 − 4 = 1500 |

## Build It

```python
# eth_frame.py — construct and dissect Ethernet II frames
import struct, binascii

def parse_mac(b: bytes) -> str:
    return ':'.join(f'{x:02X}' for x in b)

def mac_flags(b: bytes) -> dict:
    first = b[0]
    return {
        'is_multicast': bool(first & 0x01),   # I/G bit
        'is_local':     bool(first & 0x02),   # U/L bit
    }

def dissect(frame: bytes) -> dict:
    """Dissect a raw Ethernet frame (preamble already stripped)."""
    if len(frame) < 14:
        raise ValueError(f"Frame too short: {len(frame)} bytes")
    dst = frame[0:6]
    src = frame[6:12]
    tl  = struct.unpack('!H', frame[12:14])[0]

    result = {
        'dst_mac':   parse_mac(dst),
        'src_mac':   parse_mac(src),
        'dst_flags': mac_flags(dst),
        'src_flags': mac_flags(src),
    }

    if tl >= 1536:
        result['type'] = 'Ethernet II'
        result['ethertype'] = f'0x{tl:04X}'
        result['payload'] = frame[14:-4]
    elif tl <= 1500:
        result['type'] = 'IEEE 802.3'
        result['length'] = tl
        result['dsap'] = f'0x{frame[14]:02X}' if len(frame) > 14 else None
        result['ssap'] = f'0x{frame[15]:02X}' if len(frame) > 15 else None
        result['payload'] = frame[17:17 + tl - 3]  # subtract 3 LLC header bytes
    else:
        result['type'] = 'RESERVED (discard)'

    fcs_val = struct.unpack('<I', frame[-4:])[0]
    computed = binascii.crc32(frame[:-4]) & 0xFFFFFFFF
    result['fcs_ok'] = (fcs_val == computed)
    return result


def build_eth2(dst: bytes, src: bytes, ethertype: int, payload: bytes) -> bytes:
    """Build a minimal valid Ethernet II frame with correct FCS and padding."""
    assert len(dst) == 6 and len(src) == 6
    assert 0x0600 <= ethertype <= 0xFFFF
    padded = payload.ljust(46, b'\x00')[:1500]
    header = dst + src + struct.pack('!H', ethertype)
    frame_no_fcs = header + padded
    fcs = struct.pack('<I', binascii.crc32(frame_no_fcs) & 0xFFFFFFFF)
    return frame_no_fcs + fcs


if __name__ == '__main__':
    dst = bytes([0xFF]*6)          # broadcast
    src = bytes([0x00,0x1A,0x2B,0x10,0x20,0x30])
    frame = build_eth2(dst, src, 0x0800, b'Hello')
    print(f"Frame length: {len(frame)} bytes (min 64)")
    info = dissect(frame)
    for k, v in info.items():
        print(f"  {k}: {v}")
```

Run with:
```
python3 eth_frame.py
```

Expected output shows a 64-byte frame (payload padded to 46 bytes), FCS OK, dst_flags showing is_multicast=True for broadcast.

## Use It

| Scenario | What to check |
|----------|--------------|
| Parse a pcap in Wireshark | Filter `eth.type == 0x0800` for IPv4; `eth.len` for 802.3 frames |
| Identify multicast frames | Wireshark: `eth.dst[0:1] & 01:00:00:00:00:00 == 01:00:00:00:00:00` |
| Find locally administered MACs | Wireshark: `eth.src[0:1] & 02:00:00:00:00:00 == 02:00:00:00:00:00` |
| Verify FCS | Enable FCS display; look for "Bad FCS" expert info items |
| Detect VLAN-tagged frames | Wireshark: `eth.type == 0x8100`; check VLAN ID in TCI field |

## Ship It

The `dissect()` function is a self-contained diagnostic tool. Use it in a capture pipeline:

```python
# Minimal pcap reader feeding dissect()
import struct

def pcap_frames(path):
    with open(path, 'rb') as f:
        f.read(24)  # global header
        while True:
            hdr = f.read(16)
            if len(hdr) < 16: break
            _, _, incl, _ = struct.unpack('<IIII', hdr)
            yield f.read(incl)

for raw in pcap_frames('capture.pcap'):
    info = dissect(raw)
    print(info['dst_mac'], info.get('ethertype', info.get('length')), 'FCS OK' if info['fcs_ok'] else 'FCS BAD')
```

## Exercises

1. **Type/Length boundary:** Write a Python function that takes a raw frame as `bytes` and returns `'Ethernet II'`, `'IEEE 802.3'`, or `'RESERVED'` based on the value at offset 12. Test it against three synthesized frames: one with EtherType `0x0800`, one with Length `60`, and one with value `0x05FE`.

2. **Multicast MAC derivation:** IPv4 multicast address `239.1.2.3` maps to Ethernet multicast `01:00:5E:01:02:03`. Explain the mapping rule, identify which bits of the IPv4 address are dropped, and give the Ethernet multicast MAC for `224.0.0.251` (mDNS).

3. **Minimum frame analysis:** A DNS query payload is 28 bytes. Determine: (a) the PAD size added, (b) the total on-wire frame size, (c) what the receiver uses to know that the last 18 bytes are padding rather than DNS data.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| EtherType | "Layer 3 protocol field" | 2-byte field at offset 12 with value ≥ 0x0600; identifies encapsulated protocol per IEEE RAand IANA registry |
| I/G bit | "multicast bit" | Individual/Group bit: bit 0 of first byte of MAC address; 0 = unicast, 1 = multicast or broadcast |
| U/L bit | "locally administered bit" | Universally/Locally administered bit: bit 1 of first byte; 0 = OUI assigned by IEEE, 1 = locally configured |
| OUI | "vendor prefix" | Organizationally Unique Identifier; 24-bit prefix of a MAC address assigned to a vendor by the IEEE Registration Authority |
| FCS | "the CRC at the end" | Frame Check Sequence; 4-byte CRC-32 over Dst through Data/Pad; not part of the 1500-byte MTU |
| PAD | "padding bytes" | Zero bytes appended by sender NIC to reach the 46-byte minimum payload; invisible to network layer |
| 802.1Q | "VLAN tagging" | IEEE standard inserting a 4-byte tag between Src MAC and EtherType; adds PCP, DEI, and 12-bit VLAN ID |
| LLC | "802.2 header" | Logical Link Control sub-layer; 3-byte header (DSAP, SSAP, Control) that follows the Length field in IEEE 802.3 frames |

## Further Reading

- **IEEE 802.3-2022**, Clause 3 — Normative frame format definition, Type/Length disambiguation rule, and minimum/maximum size constraints.
- **IEEE 802.1Q-2022** — VLAN tagging, 0x8100 TPID, TCI field structure.
- **RFC 894** (1984) — Standard for transmission of IP datagrams over Ethernet; specifies EtherType 0x0800 and the 1500-byte MTU.
- **RFC 1042** (1988) — Transmission of IP over IEEE 802 networks; explains LLC/SNAP encapsulation used in 802.3-Length-mode frames.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Section 4.3.2 — Ethernet MAC sublayer, frame format, address structure.
