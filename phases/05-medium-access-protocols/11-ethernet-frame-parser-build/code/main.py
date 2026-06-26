"""
Ethernet Frame Parser — Ethernet II vs IEEE 802.3 Disambiguation

Demonstrates:
  - Parsing raw Ethernet frames and classifying them as Ethernet II,
    IEEE 802.3, VLAN-tagged, or RESERVED based on the 2-byte
    Length/Type field at offset 12 (≥1536 → EtherType; ≤1500 → Length;
    1501-1535 → discard)
  - Decoding 802.1Q VLAN tags (EtherType 0x8100) and QinQ double tags
    (outer 0x88A8 S-tag, inner 0x8100 C-tag)
  - Extracting LLC (DSAP/SSAP/Control) and SNAP (OUI + PID) sub-headers
    from IEEE 802.3 frames
  - FCS verification via CRC-32 comparison

No third-party dependencies — stdlib only.
Run:  python3 main.py
"""

import struct
import binascii
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ETHERTYPE_8021Q  = 0x8100   # 802.1Q VLAN tag
ETHERTYPE_8021AD = 0x88A8   # QinQ outer S-tag
DSAP_SNAP = 0xAA            # SNAP Service Access Point
DSAP_STP  = 0x42            # STP/RSTP BPDUs
DSAP_ISIS = 0xFE            # OSI IS-IS
DSAP_IPX  = 0xE0            # Novell IPX

ETHERTYPE_NAMES: dict[int, str] = {
    0x0800: "IPv4",
    0x0806: "ARP",
    0x86DD: "IPv6",
    0x8100: "802.1Q",
    0x88A8: "802.1ad (QinQ)",
    0x88CC: "LLDP",
    0x8847: "MPLS",
    0x8137: "Novell IPX",
    0x0600: "XNS",
}

DSAP_NAMES: dict[int, str] = {
    0x42: "STP/RSTP BPDU",
    0xAA: "SNAP",
    0xFE: "OSI IS-IS",
    0xE0: "Novell IPX",
}


# ---------------------------------------------------------------------------
# ParsedFrame dataclass
# ---------------------------------------------------------------------------

@dataclass
class ParsedFrame:
    dst_mac:    str
    src_mac:    str
    frame_type: str             # 'Ethernet II', 'IEEE 802.3', 'VLAN-tagged', 'RESERVED', 'TRUNCATED'
    ethertype:  Optional[int]  = None
    proto_name: Optional[str]  = None
    vlan_ids:   list           = field(default_factory=list)
    length:     Optional[int]  = None
    dsap:       Optional[int]  = None
    ssap:       Optional[int]  = None
    control:    Optional[int]  = None
    snap_oui:   Optional[bytes]= None
    snap_pid:   Optional[int]  = None
    payload:    bytes          = b""
    fcs_ok:     bool           = False
    errors:     list           = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_mac(b: bytes) -> str:
    return ":".join(f"{x:02X}" for x in b)


def _check_fcs(frame: bytes) -> bool:
    """Verify FCS: compare last 4 bytes (little-endian CRC-32) vs recomputed."""
    if len(frame) < 4:
        return False
    on_wire  = struct.unpack("<I", frame[-4:])[0]
    computed = binascii.crc32(frame[:-4]) & 0xFFFFFFFF
    return on_wire == computed


def _make_fcs(data: bytes) -> bytes:
    """Append little-endian CRC-32 FCS to raw header+payload bytes."""
    return struct.pack("<I", binascii.crc32(data) & 0xFFFFFFFF)


# ---------------------------------------------------------------------------
# Frame builder helpers  (used by tests and demos)
# ---------------------------------------------------------------------------

def build_ethernet_ii(dst: bytes, src: bytes, ethertype: int, payload: bytes) -> bytes:
    """Build a minimal valid Ethernet II frame (preamble stripped, FCS appended)."""
    payload = payload.ljust(46, b"\x00")    # enforce 64-byte minimum
    header  = dst + src + struct.pack("!H", ethertype) + payload
    return header + _make_fcs(header)


def build_ieee8023(dst: bytes, src: bytes, dsap: int, ssap: int, data: bytes) -> bytes:
    """Build a minimal IEEE 802.3 frame with 3-byte LLC header."""
    llc  = bytes([dsap, ssap, 0x03]) + data
    llc  = llc.ljust(46, b"\x00")
    body = dst + src + struct.pack("!H", len(llc)) + llc
    return body + _make_fcs(body)


def build_snap_frame(dst: bytes, src: bytes, oui: bytes, pid: int, data: bytes) -> bytes:
    """Build an IEEE 802.3 frame with SNAP sub-header (DSAP=0xAA, SSAP=0xAA)."""
    snap_hdr = oui + struct.pack("!H", pid)
    llc      = bytes([DSAP_SNAP, DSAP_SNAP, 0x03]) + snap_hdr + data
    llc      = llc.ljust(46, b"\x00")
    body     = dst + src + struct.pack("!H", len(llc)) + llc
    return body + _make_fcs(body)


def build_vlan_tagged(dst: bytes, src: bytes, vlan_id: int,
                       inner_ethertype: int, payload: bytes,
                       outer_tpid: int = ETHERTYPE_8021Q) -> bytes:
    """Build a VLAN-tagged (802.1Q) Ethernet frame."""
    tci     = vlan_id & 0x0FFF
    payload = payload.ljust(46, b"\x00")
    body    = (dst + src
               + struct.pack("!HH", outer_tpid, tci)
               + struct.pack("!H", inner_ethertype)
               + payload)
    return body + _make_fcs(body)


def build_qinq(dst: bytes, src: bytes, svlan: int, cvlan: int,
               inner_ethertype: int, payload: bytes) -> bytes:
    """Build a QinQ (double-tagged) frame: outer 0x88A8 S-tag, inner 0x8100 C-tag."""
    payload = payload.ljust(46, b"\x00")
    body    = (dst + src
               + struct.pack("!HH", ETHERTYPE_8021AD, svlan & 0x0FFF)
               + struct.pack("!HH", ETHERTYPE_8021Q,  cvlan & 0x0FFF)
               + struct.pack("!H", inner_ethertype)
               + payload)
    return body + _make_fcs(body)


# ---------------------------------------------------------------------------
# Core parser  (implements the parsing decision tree from the lesson)
# ---------------------------------------------------------------------------

def parse_frame(raw: bytes) -> ParsedFrame:
    """
    Parse a raw Ethernet frame (preamble stripped, FCS included).

    Decision tree (frame[12:14] as uint16 = V):
      V == 0x8100 / 0x88A8  →  VLAN-tagged: strip 4-byte tag, loop
      V >= 1536             →  Ethernet II (EtherType = V)
      V <= 1500             →  IEEE 802.3  (Length = V, read LLC header)
      1501 <= V <= 1535     →  RESERVED: discard
    """
    if len(raw) < 14:
        return ParsedFrame("", "", "TRUNCATED",
                           errors=[f"Too short: {len(raw)} bytes"])

    result = ParsedFrame(
        dst_mac    = _parse_mac(raw[0:6]),
        src_mac    = _parse_mac(raw[6:12]),
        frame_type = "unknown",
        fcs_ok     = _check_fcs(raw),
    )

    offset = 12     # current position of the EtherType/Length field

    # --- Step 1: unwrap VLAN tags -----------------------------------------
    while True:
        if offset + 2 > len(raw) - 4:
            result.errors.append("Truncated at EtherType/Length")
            result.frame_type = "TRUNCATED"
            return result
        tl = struct.unpack("!H", raw[offset:offset + 2])[0]
        if tl in (ETHERTYPE_8021Q, ETHERTYPE_8021AD):
            if offset + 4 > len(raw) - 4:
                result.errors.append("Truncated VLAN tag")
                result.frame_type = "TRUNCATED"
                return result
            tci     = struct.unpack("!H", raw[offset + 2:offset + 4])[0]
            vid     = tci & 0x0FFF
            result.vlan_ids.append(vid)
            offset += 4     # skip TPID (2 bytes) + TCI (2 bytes)
        else:
            break

    tl            = struct.unpack("!H", raw[offset:offset + 2])[0]
    payload_start = offset + 2

    if result.vlan_ids:
        result.frame_type = "VLAN-tagged"

    # --- Step 2: classify on the value of tl --------------------------------
    if 1501 <= tl <= 1535:
        result.frame_type = "RESERVED"
        result.errors.append(f"Reserved EtherType/Length value: 0x{tl:04X}")
        return result

    if tl >= 1536:
        # ---- Ethernet II ----
        if not result.vlan_ids:
            result.frame_type = "Ethernet II"
        result.ethertype  = tl
        result.proto_name = ETHERTYPE_NAMES.get(tl, f"0x{tl:04X}")
        result.payload    = raw[payload_start:-4]

    else:
        # ---- IEEE 802.3 (tl == declared payload length) ----
        if not result.vlan_ids:
            result.frame_type = "IEEE 802.3"
        result.length = tl

        if payload_start + 3 > len(raw) - 4:
            result.errors.append("Truncated LLC header")
            return result

        result.dsap    = raw[payload_start]
        result.ssap    = raw[payload_start + 1]
        result.control = raw[payload_start + 2]
        llc_data_start = payload_start + 3

        if result.dsap == DSAP_SNAP and result.ssap == DSAP_SNAP:
            # SNAP extension: 3-byte OUI + 2-byte Protocol ID
            if llc_data_start + 5 > len(raw) - 4:
                result.errors.append("Truncated SNAP header")
                return result
            result.snap_oui = raw[llc_data_start:llc_data_start + 3]
            result.snap_pid = struct.unpack("!H", raw[llc_data_start + 3:llc_data_start + 5])[0]
            if result.snap_oui == b"\x00\x00\x00":
                # OUI=0x000000 means the PID is in the EtherType namespace
                result.ethertype  = result.snap_pid
                result.proto_name = ETHERTYPE_NAMES.get(result.snap_pid, f"0x{result.snap_pid:04X}")
            result.payload = raw[llc_data_start + 5:payload_start + tl]
        else:
            result.proto_name = DSAP_NAMES.get(result.dsap, f"DSAP=0x{result.dsap:02X}")
            result.payload    = raw[llc_data_start:payload_start + tl]

    return result


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

SEP  = "─" * 64
SEP2 = "═" * 64

def _print_frame(label: str, raw: bytes, pf: ParsedFrame) -> None:
    print(f"\n  {label}")
    print(f"  {SEP}")
    print(f"  Wire ({len(raw)} B): {raw.hex()[:72]}{'…' if len(raw.hex()) > 72 else ''}")
    print(f"  Dst MAC    : {pf.dst_mac}")
    print(f"  Src MAC    : {pf.src_mac}")
    print(f"  Frame type : {pf.frame_type}")
    if pf.vlan_ids:
        print(f"  VLAN IDs   : {pf.vlan_ids}")
    if pf.ethertype is not None:
        print(f"  EtherType  : 0x{pf.ethertype:04X}  ({pf.proto_name})")
    if pf.length is not None:
        print(f"  Length     : {pf.length} bytes")
    if pf.dsap is not None:
        print(f"  LLC DSAP   : 0x{pf.dsap:02X}  SSAP=0x{pf.ssap:02X}  Ctrl=0x{pf.control:02X}")
        if pf.proto_name:
            print(f"  Protocol   : {pf.proto_name}")
    if pf.snap_oui is not None:
        print(f"  SNAP OUI   : {pf.snap_oui.hex()}  PID=0x{pf.snap_pid:04X}")
    print(f"  Payload    : {len(pf.payload)} B")
    print(f"  FCS        : {'OK' if pf.fcs_ok else 'BAD'}")
    if pf.errors:
        for e in pf.errors:
            print(f"  ERROR      : {e}")


# ---------------------------------------------------------------------------
# Built-in test suite
# ---------------------------------------------------------------------------

BC  = bytes([0xFF] * 6)
SRC = bytes([0x00, 0x11, 0x22, 0x33, 0x44, 0x55])
DST = bytes([0x00, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE])


def _run_tests() -> None:
    print(f"\n{SEP2}")
    print("  Built-in test suite")
    print(SEP2)

    passed = 0

    # Test 1: Ethernet II IPv4
    raw = build_ethernet_ii(BC, SRC, 0x0800, b"X" * 20)
    pf  = parse_frame(raw)
    assert pf.frame_type == "Ethernet II", f"T1: {pf.frame_type}"
    assert pf.ethertype  == 0x0800
    assert pf.proto_name == "IPv4"
    assert pf.fcs_ok
    print(f"  [PASS] T1: Ethernet II IPv4")
    passed += 1

    # Test 2: Ethernet II ARP
    raw = build_ethernet_ii(BC, SRC, 0x0806, b"A" * 28)
    pf  = parse_frame(raw)
    assert pf.frame_type == "Ethernet II"
    assert pf.ethertype  == 0x0806
    assert pf.proto_name == "ARP"
    print(f"  [PASS] T2: Ethernet II ARP")
    passed += 1

    # Test 3: IEEE 802.3 STP BPDU (DSAP=0x42)
    raw = build_ieee8023(BC, SRC, 0x42, 0x42, b"\x00" * 10)
    pf  = parse_frame(raw)
    assert pf.frame_type == "IEEE 802.3", f"T3: {pf.frame_type}"
    assert pf.dsap       == 0x42
    assert pf.ssap       == 0x42
    assert "STP" in pf.proto_name
    print(f"  [PASS] T3: IEEE 802.3 STP BPDU (DSAP=0x42)")
    passed += 1

    # Test 4: Reserved range (1501–1535)
    raw  = BC + SRC + struct.pack("!H", 0x05FF) + bytes(46)
    raw += _make_fcs(raw)
    pf   = parse_frame(raw)
    assert pf.frame_type == "RESERVED", f"T4: {pf.frame_type}"
    print(f"  [PASS] T4: Reserved EtherType/Length (0x05FF = 1535)")
    passed += 1

    # Test 5: VLAN-tagged (802.1Q, VLAN 100, inner IPv4)
    raw = build_vlan_tagged(BC, SRC, vlan_id=100, inner_ethertype=0x0800,
                             payload=b"P" * 20)
    pf  = parse_frame(raw)
    assert pf.frame_type == "VLAN-tagged", f"T5: {pf.frame_type}"
    assert pf.vlan_ids   == [100]
    assert pf.ethertype  == 0x0800
    assert pf.proto_name == "IPv4"
    print(f"  [PASS] T5: 802.1Q VLAN-tagged (VID=100, inner IPv4)")
    passed += 1

    # Test 6: QinQ double-tagged (SVLAN=200, CVLAN=100, inner IPv6)
    raw = build_qinq(BC, SRC, svlan=200, cvlan=100,
                     inner_ethertype=0x86DD, payload=b"P" * 40)
    pf  = parse_frame(raw)
    assert pf.frame_type == "VLAN-tagged", f"T6: {pf.frame_type}"
    assert pf.vlan_ids   == [200, 100], f"T6 vlan_ids: {pf.vlan_ids}"
    assert pf.ethertype  == 0x86DD
    assert pf.proto_name == "IPv6"
    print(f"  [PASS] T6: QinQ double-tagged (SVLAN=200, CVLAN=100, inner IPv6)")
    passed += 1

    # Test 7: SNAP frame (DSAP=0xAA, OUI=00:00:00, PID=0x8137 Novell IPX)
    raw = build_snap_frame(DST, SRC, oui=b"\x00\x00\x00", pid=0x8137,
                            data=b"\xDE\xAD\xBE\xEF" * 5)
    pf  = parse_frame(raw)
    assert pf.frame_type == "IEEE 802.3", f"T7: {pf.frame_type}"
    assert pf.dsap       == DSAP_SNAP
    assert pf.ssap       == DSAP_SNAP
    assert pf.snap_oui   == b"\x00\x00\x00"
    assert pf.snap_pid   == 0x8137
    assert pf.ethertype  == 0x8137
    print(f"  [PASS] T7: SNAP frame (OUI=00:00:00, PID=0x8137 Novell IPX)")
    passed += 1

    # Test 8: FCS corruption detected → fcs_ok == False
    raw        = build_ethernet_ii(BC, SRC, 0x0800, b"integrity" + b"\x00" * 37)
    corrupted  = bytearray(raw)
    corrupted[20] ^= 0xFF   # flip a byte in the payload
    pf         = parse_frame(bytes(corrupted))
    assert not pf.fcs_ok, "T8: corrupted frame should have fcs_ok=False"
    print(f"  [PASS] T8: FCS corruption detected")
    passed += 1

    # Test 9: truncated input (< 14 bytes) → TRUNCATED, no exception
    pf = parse_frame(b"\xFF\xFF\xFF\xFF\xFF\xFF\x00\x11\x22")
    assert pf.frame_type == "TRUNCATED"
    assert pf.errors
    print(f"  [PASS] T9: Truncated input handled gracefully")
    passed += 1

    print(f"\n  {passed}/9 tests passed")


# ---------------------------------------------------------------------------
# main — demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    print(SEP2)
    print("  Ethernet Frame Parser — Ethernet II vs IEEE 802.3 Disambiguation")
    print(SEP2)
    print()
    print("  The 2-byte field at offset 12 determines the frame format:")
    print("    ≥ 1536 (0x0600)  →  EtherType  (Ethernet II / DIX)")
    print("    ≤ 1500 (0x05DC)  →  Length     (IEEE 802.3 + LLC)")
    print("    1501–1535        →  RESERVED   (discard)")
    print("    0x8100 / 0x88A8  →  VLAN tag   (strip and re-read)")

    # ── Demo 1: Ethernet II IPv4 ───────────────────────────────────────────
    raw1 = build_ethernet_ii(
        dst=bytes.fromhex("ffffffffffff"),
        src=bytes.fromhex("001122334455"),
        ethertype=0x0800,
        payload=bytes([0x45, 0x00, 0x00, 0x3C]) + b"\xDE\xAD" * 20,
    )
    pf1 = parse_frame(raw1)
    _print_frame("Demo 1 — Ethernet II (IPv4 broadcast)", raw1, pf1)

    # ── Demo 2: IEEE 802.3 STP BPDU ───────────────────────────────────────
    raw2 = build_ieee8023(
        dst=bytes.fromhex("0180C2000000"),   # STP multicast
        src=bytes.fromhex("001122334455"),
        dsap=0x42, ssap=0x42,
        data=b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00",
    )
    pf2 = parse_frame(raw2)
    _print_frame("Demo 2 — IEEE 802.3 STP BPDU (DSAP=0x42, SSAP=0x42)", raw2, pf2)

    # ── Demo 3: 802.1Q VLAN-tagged IPv4 ───────────────────────────────────
    raw3 = build_vlan_tagged(
        dst=bytes.fromhex("ffffffffffff"),
        src=bytes.fromhex("001122334455"),
        vlan_id=100,
        inner_ethertype=0x0800,
        payload=b"\x45\x00" + b"\xBE\xEF" * 20,
    )
    pf3 = parse_frame(raw3)
    _print_frame("Demo 3 — 802.1Q VLAN-tagged (VID=100, inner IPv4)", raw3, pf3)

    # ── Demo 4: QinQ (double-tagged) IPv6 ─────────────────────────────────
    raw4 = build_qinq(
        dst=bytes.fromhex("ffffffffffff"),
        src=bytes.fromhex("001122334455"),
        svlan=200, cvlan=100,
        inner_ethertype=0x86DD,
        payload=b"\x60" + b"\x00" * 39,
    )
    pf4 = parse_frame(raw4)
    _print_frame("Demo 4 — QinQ double-tagged (SVLAN=200, CVLAN=100, inner IPv6)", raw4, pf4)

    # ── Demo 5: IEEE 802.3 + SNAP (Novell IPX) ────────────────────────────
    raw5 = build_snap_frame(
        dst=bytes.fromhex("ffffffffffff"),
        src=bytes.fromhex("001122334455"),
        oui=b"\x00\x00\x00",   # EtherType namespace
        pid=0x8137,             # Novell IPX
        data=b"\xDE\xAD\xBE\xEF" * 5,
    )
    pf5 = parse_frame(raw5)
    _print_frame("Demo 5 — IEEE 802.3 + SNAP (OUI=00:00:00, PID=0x8137 Novell IPX)", raw5, pf5)

    # ── Demo 6: Reserved range ─────────────────────────────────────────────
    raw6  = bytes.fromhex("ffffffffffff") + bytes.fromhex("001122334455")
    raw6 += struct.pack("!H", 0x05FF)   # 1535 → RESERVED
    raw6 += bytes(46)
    raw6 += _make_fcs(raw6)
    pf6   = parse_frame(raw6)
    _print_frame("Demo 6 — RESERVED range (0x05FF = 1535)", raw6, pf6)

    # ── Demo 7: classification table ──────────────────────────────────────
    print(f"\n  {SEP}")
    print("  Demo 7 — Length/Type field disambiguation table")
    print(f"  {SEP}")
    print(f"  {'Value':<10} {'Dec':>6}   {'Classification':<18}  Note")
    print(f"  {'─'*62}")
    cases = [
        (0x002E, "minimum payload (46 B)"),
        (0x05DC, "maximum payload (1500 B) — IEEE 802.3 max"),
        (0x05DD, "1501 — RESERVED (first forbidden value)"),
        (0x05FF, "1535 — RESERVED (last forbidden value)"),
        (0x0600, "1536 — Ethernet II threshold (XNS)"),
        (0x0800, "IPv4 EtherType"),
        (0x0806, "ARP EtherType"),
        (0x8100, "802.1Q VLAN tag"),
        (0x88A8, "802.1ad QinQ outer S-tag"),
        (0x86DD, "IPv6 EtherType"),
    ]
    for val, note in cases:
        if val <= 1500:
            cls = "IEEE 802.3 (Length)"
        elif 1501 <= val <= 1535:
            cls = "RESERVED"
        elif val in (ETHERTYPE_8021Q, ETHERTYPE_8021AD):
            cls = "VLAN tag"
        else:
            cls = "Ethernet II"
        print(f"  0x{val:04X}    {val:>6}   {cls:<18}  {note}")

    # ── Run built-in tests ─────────────────────────────────────────────────
    _run_tests()

    print()
    print(SEP2)
    print("  All demonstrations and tests completed successfully.")
    print(SEP2)


if __name__ == "__main__":
    main()
