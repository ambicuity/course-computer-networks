"""Lab: capturing beacon, probe, auth, and association frames in monitor mode.

A stdlib-only 802.11 management-frame dissector. No network calls, no third-party
libraries. The parser consumes small structured dictionaries that mirror what
Wireshark's "Export Packet Bytes" + "Packet Details" panel give you for a beacon,
or a hand-built synthetic frame for the no-hardware drill.

Run as a script to see four sample frames dissected end-to-end:

    python3 code/main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Tuple


# ---------------------------------------------------------------------------
# Channel <-> frequency mapping (802.11-2007, 2.4 GHz + 5 GHz)
# ---------------------------------------------------------------------------

# Center frequency in MHz = 2407 + 5 * ch for 2.4 GHz, 5000 + 5 * ch for 5 GHz.
_2GHZ_OFFSET = 2407
_5GHZ_OFFSET = 5000


def freq_to_channel(freq_mhz: int) -> Tuple[int, str]:
    """Return (channel, band) for a given center frequency in MHz.

    >>> freq_to_channel(2437)
    (6, '2.4')
    >>> freq_to_channel(5180)
    (36, '5')
    """
    if 2412 <= freq_mhz <= 2472:
        return (freq_mhz - _2GHZ_OFFSET) // 5, "2.4"
    if freq_mhz == 2484:
        return 14, "2.4"
    if 5000 <= freq_mhz <= 5895:
        return (freq_mhz - _5GHZ_OFFSET) // 5, "5"
    raise ValueError(f"freq_to_channel: unsupported frequency {freq_mhz} MHz")


def channel_to_freq(channel: int) -> Tuple[int, str]:
    """Return (freq_mhz, band) for a given channel number.

    >>> channel_to_freq(36)
    (5180, '5')
    >>> channel_to_freq(11)
    (2462, '2.4')
    """
    if 1 <= channel <= 13:
        return _2GHZ_OFFSET + 5 * channel, "2.4"
    if channel == 14:
        return 2484, "2.4"
    if 36 <= channel <= 165:
        return _5GHZ_OFFSET + 5 * channel, "5"
    raise ValueError(f"channel_to_freq: unsupported channel {channel}")


# ---------------------------------------------------------------------------
# Frame Control: Type (2 bits) and Subtype (4 bits) -> friendly name.
# ---------------------------------------------------------------------------

_FRAME_TYPE_NAMES: Dict[int, str] = {0: "Management", 1: "Control", 2: "Data"}

# Subtype names for management frames (Type = 0). The Type/Subtype byte
# packed by 802.11 is (subtype << 4) | type; Wireshark's wlan.fc.type_subtype.
_SUBTYPE_NAMES: Dict[int, str] = {
    0x00: "Association Request",
    0x01: "Association Response",
    0x02: "Reassociation Request",
    0x03: "Reassociation Response",
    0x04: "Probe Request",
    0x05: "Probe Response",
    0x08: "Beacon",
    0x09: "ATIM",
    0x0A: "Disassociation",
    0x0B: "Authentication",
    0x0C: "Deauthentication",
    0x0D: "Action",
    0x0E: "Action No Ack",
}


def decode_type_subtype(type_subtype: int) -> Tuple[str, str]:
    """Return (frame_type, subtype_name) for a wlan.fc.type_subtype byte.

    >>> decode_type_subtype(0x08)
    ('Management', 'Beacon')
    >>> decode_type_subtype(0x04)
    ('Management', 'Probe Request')
    """
    ftype = type_subtype & 0x03
    subtype = (type_subtype >> 2) & 0x0F
    type_name = _FRAME_TYPE_NAMES.get(ftype, f"Type-{ftype}")
    subtype_name = _SUBTYPE_NAMES.get(subtype, f"Subtype-{subtype}")
    return type_name, subtype_name


# ---------------------------------------------------------------------------
# Information Element tag dictionary.
# ---------------------------------------------------------------------------

# Tag (1 byte) -> friendly name and a hint about the payload shape.
_IE_NAMES: Dict[int, str] = {
    0: "SSID",
    1: "Supported Rates",
    2: "FH Parameter Set",
    3: "DS Parameter Set",
    4: "CF Parameter Set",
    5: "TIM",
    6: "IBSS Parameter Set",
    7: "Country",
    8: "Hopping Pattern Parameters",
    9: "Hopping Pattern Table",
    10: "Request",
    11: "BSS Load",
    12: "Power Constraint",
    13: "Power Capability",
    14: "TPC Request",
    15: "TPC Report",
    16: "Supported Channels",
    17: "Channel Switch Announcement",
    18: "Measurement Request",
    19: "Measurement Report",
    20: "Quiet",
    21: "IBSS DFS",
    22: "ERP",
    23: "TSPEC",
    24: "TCLAS",
    25: "Schedule",
    32: "Power Configuration",
    33: "Power Status",
    34: "TIM Broadcast Request",
    35: "TIM Broadcast Response",
    36: "QoS Capability",
    37: "ERP Information",
    42: "HT Capabilities (802.11n)",
    45: "HT Capabilities (alias)",
    46: "QoS Traffic Capability",
    48: "RSN (WPA2/WPA3)",
    50: "Extended Supported Rates",
    58: "CCX Extended Capabilities",
    61: "HT Operation",
    70: "RM Enabled Capabilities",
    100: "BSS Membership Selectors (VHT/HE)",
    127: "Extended Capabilities",
    150: "Transmit Power Envelope",
    191: "HT Information",
    221: "Vendor Specific",
}


def ie_name(tag: int) -> str:
    """Return the friendly IE name for a tag number, e.g. 0 -> 'SSID'."""
    return _IE_NAMES.get(tag, f"Unknown-{tag}")


# ---------------------------------------------------------------------------
# Information Element body parser.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InformationElement:
    """One tag-length-value block from a management frame body."""

    tag: int
    payload: bytes

    @property
    def name(self) -> str:
        return ie_name(self.tag)

    @property
    def length(self) -> int:
        return len(self.payload)

    def payload_hex(self) -> str:
        return " ".join(f"{b:02x}" for b in self.payload)


def parse_information_elements(body: bytes) -> List[InformationElement]:
    """Walk a tag-length-value chain and return one entry per IE.

    Robust against malformed tails: any final byte without room for a length
    byte is dropped silently, mirroring tshark's behaviour on corrupted IEs.

    >>> parse_information_elements(bytes.fromhex("0003aabbcc"))[0].name
    'SSID'
    """
    ies: List[InformationElement] = []
    cursor = 0
    n = len(body)
    while cursor + 2 <= n:
        tag = body[cursor]
        length = body[cursor + 1]
        cursor += 2
        if cursor + length > n:
            break
        ies.append(InformationElement(tag=tag, payload=bytes(body[cursor:cursor + length])))
        cursor += length
    return ies


# ---------------------------------------------------------------------------
# Management frame parsers.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParsedFrame:
    """Common fields shared by every parsed management frame."""

    timestamp: int
    bssid: str
    source: str
    frame_type: str
    subtype: str
    type_subtype_hex: str
    channel: int
    frequency_mhz: int
    band: str
    information_elements: Tuple[InformationElement, ...] = field(default_factory=tuple)

    # ---- helpers used by the dissector printer ----
    def ie_by_tag(self, tag: int) -> Optional[InformationElement]:
        for ie in self.information_elements:
            if ie.tag == tag:
                return ie
        return None

    @property
    def ssid(self) -> str:
        ie = self.ie_by_tag(0)
        if ie is None or ie.length == 0:
            return "<broadcast>"
        try:
            return ie.payload.decode("utf-8")
        except UnicodeDecodeError:
            return ie.payload_hex()

    @property
    def supported_rates(self) -> str:
        ie = self.ie_by_tag(1)
        if ie is None:
            return ""
        return ", ".join(f"{(b & 0x7F) * 500} kbps" for b in ie.payload)

    @property
    def rsn_summary(self) -> str:
        ie = self.ie_by_tag(48)
        if ie is None or ie.length < 8:
            return ""
        # RSN version is the first 2 bytes; the rest is suite selectors.
        return f"RSN version {int.from_bytes(ie.payload[:2], 'little')}, " f"{ie.length - 2} bytes of suite data"


def _common(
    timestamp: int,
    bssid: str,
    source: str,
    type_subtype: int,
    channel: int,
    ies: Tuple[InformationElement, ...],
) -> ParsedFrame:
    type_name, subtype_name = decode_type_subtype(type_subtype)
    freq_mhz, band = channel_to_freq(channel)
    return ParsedFrame(
        timestamp=timestamp,
        bssid=bssid,
        source=source,
        frame_type=type_name,
        subtype=subtype_name,
        type_subtype_hex=f"0x{type_subtype:02x}",
        channel=channel,
        frequency_mhz=freq_mhz,
        band=band,
        information_elements=ies,
    )


def parse_beacon(frame: Mapping[str, object]) -> ParsedFrame:
    """Parse a beacon frame dict.

    Required keys: timestamp, bssid, source, channel, body (bytes or hex str).
    Optional: type_subtype (defaults to 0x08, the beacon subtype).
    """
    body = _coerce_body(frame["body"])
    ies = tuple(parse_information_elements(body))
    return _common(
        timestamp=int(frame["timestamp"]),
        bssid=str(frame["bssid"]),
        source=str(frame.get("source", frame["bssid"])),
        type_subtype=int(frame.get("type_subtype", 0x08)),
        channel=int(frame["channel"]),
        ies=ies,
    )


def parse_probe_req(frame: Mapping[str, object]) -> ParsedFrame:
    """Parse a probe request (subtype 0x04). Source = the client's MAC."""
    body = _coerce_body(frame["body"])
    ies = tuple(parse_information_elements(body))
    return _common(
        timestamp=int(frame["timestamp"]),
        bssid=str(frame.get("bssid", "ff:ff:ff:ff:ff:ff")),
        source=str(frame["source"]),
        type_subtype=int(frame.get("type_subtype", 0x04)),
        channel=int(frame["channel"]),
        ies=ies,
    )


def parse_auth(frame: Mapping[str, object]) -> ParsedFrame:
    """Parse an authentication frame (subtype 0x0B)."""
    body = _coerce_body(frame["body"])
    ies = tuple(parse_information_elements(body))
    return _common(
        timestamp=int(frame["timestamp"]),
        bssid=str(frame["bssid"]),
        source=str(frame["source"]),
        type_subtype=int(frame.get("type_subtype", 0x0B)),
        channel=int(frame["channel"]),
        ies=ies,
    )


def parse_assoc_req(frame: Mapping[str, object]) -> ParsedFrame:
    """Parse an association request (subtype 0x00)."""
    body = _coerce_body(frame["body"])
    ies = tuple(parse_information_elements(body))
    return _common(
        timestamp=int(frame["timestamp"]),
        bssid=str(frame["bssid"]),
        source=str(frame["source"]),
        type_subtype=int(frame.get("type_subtype", 0x00)),
        channel=int(frame["channel"]),
        ies=ies,
    )


def _coerce_body(value: object) -> bytes:
    """Accept either raw bytes or a hex string, return bytes."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        cleaned = value.replace(" ", "").replace("\n", "")
        return bytes.fromhex(cleaned)
    raise TypeError(f"body must be bytes or hex str, got {type(value).__name__}")


# ---------------------------------------------------------------------------
# Pretty printer used by __main__.
# ---------------------------------------------------------------------------

def render(frame: ParsedFrame) -> str:
    """Return a small dissection card for one parsed frame."""
    lines = [
        f"  Subtype      : {frame.subtype} ({frame.type_subtype_hex}, {frame.frame_type})",
        f"  Timestamp    : {frame.timestamp}",
        f"  Source MAC   : {frame.source}",
        f"  BSSID        : {frame.bssid}",
        f"  Channel      : {frame.channel}  ->  {frame.frequency_mhz} MHz ({frame.band} GHz)",
        f"  SSID         : {frame.ssid}",
        f"  Rates        : {frame.supported_rates or '<none reported>'}",
    ]
    rsn = frame.rsn_summary
    if rsn:
        lines.append(f"  RSN          : {rsn}")
    if frame.information_elements:
        lines.append("  IEs          :")
        for ie in frame.information_elements:
            lines.append(
                f"    tag {ie.tag:3d} ({ie.name:32s}) "
                f"length={ie.length:3d} payload={ie.payload_hex()}"
            )
    else:
        lines.append("  IEs          : <none>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sample frames. Each "body" is a hex dump of the IE chain after the fixed
# fields (timestamp, beacon interval, capability). Synthesized from the
# Wireshark user's-guide example structure for a 5 GHz 802.11n AP with
# WPA2-Personal and an HT Information IE.
# ---------------------------------------------------------------------------

SAMPLE_FRAMES: Dict[str, Dict[str, object]] = {
    "beacon_guest_wifi": {
        "timestamp": 1_716_500_000_000_000,
        "bssid": "aa:bb:cc:11:22:33",
        "source": "aa:bb:cc:11:22:33",
        "channel": 36,
        # SSID "Guest-WiFi", Supported Rates 6/9/12/18/24/36/48/54, DS 36, HT Caps,
        # HT Info, RSN WPA2-PSK/CCMP, Vendor (WPS).
        "body": (
            "00"  # SSID tag
            "09"
            "47756573742d57694669"  # "Guest-WiFi"
            "01"  # Supported Rates
            "08"
            "0c1218243048606c"
            "03"  # DS Parameter Set
            "01"
            "24"
            "2d"  # HT Capabilities (tag 45)
            "1a"
            "010c00000000000000000000000000000000000000000000000000"
            "3d"  # HT Information (tag 61)
            "16"
            "24000000000000000000000000000000000000000000"
            "30"  # RSN (tag 48)
            "14"
            "0100"
            + ("00" * 18)
            + "dd"  # Vendor Specific (WPS)
            + "06"
            + "0050f2010100"
        ),
    },
    "probe_req_hidden": {
        "timestamp": 1_716_500_010_000_000,
        "bssid": "ff:ff:ff:ff:ff:ff",
        "source": "12:34:56:78:9a:bc",
        "channel": 36,
        # Probe request: wildcard SSID (length 0), rates 24/36/48/54, HT Caps.
        "body": (
            "0000"  # SSID length 0 = wildcard
            "0104"
            "18304860"
            "2d08"
            "010c000000000000"
        ),
    },
    "auth_open": {
        "timestamp": 1_716_500_020_000_000,
        "bssid": "aa:bb:cc:11:22:33",
        "source": "12:34:56:78:9a:bc",
        "channel": 36,
        # Authentication sequence 1: algorithm=0 (Open), seq=1, status=0.
        "body": "000001000000",
    },
    "assoc_req": {
        "timestamp": 1_716_500_025_000_000,
        "bssid": "aa:bb:cc:11:22:33",
        "source": "12:34:56:78:9a:bc",
        "channel": 36,
        # Capability + 2-byte listen interval + SSID + rates + HT + RSN.
        "body": (
            "0431"
            "000a"
            "000947756573742d57694669"
            "0108"
            "0c1218243048606c"
            "2d16"
            "010c00000000000000000000000000000000000000000000"
            "3014"
            "0100" + "00" * 18
        ),
    },
}


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------

def main() -> None:
    print("802.11 management-frame dissector (stdlib only)")
    print("=" * 60)

    print("\n[1] Beacon from AP aa:bb:cc:11:22:33 (channel 36)")
    print(render(parse_beacon(SAMPLE_FRAMES["beacon_guest_wifi"])))

    print("\n[2] Probe request from client 12:34:56:78:9a:bc (wildcard SSID)")
    print(render(parse_probe_req(SAMPLE_FRAMES["probe_req_hidden"])))

    print("\n[3] Authentication seq=1, algorithm=Open")
    print(render(parse_auth(SAMPLE_FRAMES["auth_open"])))

    print("\n[4] Association request from client")
    print(render(parse_assoc_req(SAMPLE_FRAMES["assoc_req"])))

    print("\nChannel -> frequency sanity check:")
    for ch in (1, 6, 11, 36, 40, 149, 165):
        f, band = channel_to_freq(ch)
        print(f"  channel {ch:3d} -> {f} MHz ({band} GHz)")


if __name__ == "__main__":
    main()
