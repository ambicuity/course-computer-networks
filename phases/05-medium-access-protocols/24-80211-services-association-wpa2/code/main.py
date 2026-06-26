"""802.11 services: association, WPA2 EAPOL 4-way handshake simulator.

Stdlib-only teaching simulator. Models the complete station-join sequence:
  1. SSID/BSSID validation (length, unicast-bit constraints)
  2. PMK derivation via PBKDF2-HMAC-SHA1 (4 096 iterations, 256 bits)
  3. PTK derivation via PRF-384 (HMAC-SHA1 iterations, canonical Min/Max ordering)
  4. EAPOL 4-way handshake: msg1 ANonce → msg2 SNonce+MIC → msg3 GTK+MIC → msg4 ACK
  5. CCMP frame header emission with 48-bit Packet Number (PN) monotone replay counter
  6. Nine-service reference table and roaming-latency budget

MICs are HMAC-SHA256 truncations (128 bits). GTK wrapping is HMAC-SHA256(KEK, "GTK-wrap")
XOR'd with the GTK. Real WPA2 uses AES-CMAC for MICs and RFC 3394 AES Key Wrap for the GTK.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import struct
from dataclasses import dataclass, field
from typing import Final

# ── constants ────────────────────────────────────────────────────────────────
SSID_MAX_LEN: Final = 32
BSSID_LEN: Final = 6

PMK_LEN: Final = 32                      # 256 bits
KCK_LEN: Final = 16                      # 128 bits  Key Confirmation Key
KEK_LEN: Final = 16                      # 128 bits  Key Encryption Key
TK_LEN: Final = 16                       # 128 bits  Temporal Key
PTK_LEN: Final = KCK_LEN + KEK_LEN + TK_LEN  # 48 bytes = 384 bits

GTK_LEN: Final = 16                      # 128 bits
NONCE_LEN: Final = 32                    # 256 bits
MIC_LEN: Final = 16                      # 128 bits (HMAC-SHA256 truncated)
PN_MAX: Final = (1 << 48) - 1           # 48-bit packet counter ceiling

PRF_LABEL: Final = "Pairwise key expansion"

# ── validation ───────────────────────────────────────────────────────────────

def validate_ssid(ssid: bytes) -> None:
    """Enforce 802.11 SSID constraints: 0–32 octets, any 8-bit value."""
    if not isinstance(ssid, (bytes, bytearray)):
        raise TypeError(f"SSID must be bytes, got {type(ssid).__name__}")
    if len(ssid) > SSID_MAX_LEN:
        raise ValueError(
            f"SSID too long: {len(ssid)} > {SSID_MAX_LEN} octets"
        )


def validate_bssid(mac: bytes) -> None:
    """Enforce 6-byte unicast MAC address: bit 0 of octet 0 must be 0."""
    if len(mac) != BSSID_LEN:
        raise ValueError(
            f"MAC must be {BSSID_LEN} bytes, got {len(mac)}"
        )
    if mac[0] & 0x01:
        raise ValueError(
            f"MAC {mac.hex(':')} is multicast (bit 0 of octet 0 is set)"
        )


def _fmt_mac(mac: bytes) -> str:
    return ":".join(f"{b:02x}" for b in mac)


# ── PMK derivation ────────────────────────────────────────────────────────────

def derive_pmk(passphrase: str, ssid: bytes) -> bytes:
    """WPA2-Personal: PMK = PBKDF2-HMAC-SHA1(passphrase, SSID, 4096, 32).

    The 4 096-iteration count is mandated by 802.11i §8.5.1.3 for PSK mode.
    Increasing to 10 000+ (as in WPA3-R3 profile) raises the offline-attack cost.
    """
    validate_ssid(ssid)
    return hashlib.pbkdf2_hmac(
        "sha1",
        passphrase.encode("utf-8"),
        ssid,
        4096,
        dklen=PMK_LEN,
    )


# ── PRF-384 ───────────────────────────────────────────────────────────────────

def prf_384(key: bytes, label: str, data: bytes) -> bytes:
    """IEEE 802.11i PRF using HMAC-SHA1, generating PTK_LEN (48) bytes.

    PRF(K, A, B, Len) = concat of HMAC-SHA1(K, A || 0x00 || B || i)
    until Len bits are generated (§8.5.1.1).  For PTK, Len = 384.
    """
    result = b""
    prefix = label.encode("ascii") + b"\x00" + data
    counter = 0
    while len(result) < PTK_LEN:
        result += hmac.new(key, prefix + bytes([counter]), hashlib.sha1).digest()
        counter += 1
    return result[:PTK_LEN]


# ── PTK derivation ────────────────────────────────────────────────────────────

def derive_ptk(
    pmk: bytes,
    mac_a: bytes,
    mac_s: bytes,
    anonce: bytes,
    snonce: bytes,
) -> bytes:
    """Derive 384-bit PTK = PRF-384(PMK, label, Min(AA,SA)||Max(AA,SA)||Min(AN,SN)||Max(AN,SN)).

    Canonical Min/Max ordering guarantees both sides arrive at identical PRF input
    regardless of which side generated which nonce.
    """
    data = (
        min(mac_a, mac_s) + max(mac_a, mac_s) +
        min(anonce, snonce) + max(anonce, snonce)
    )
    return prf_384(pmk, PRF_LABEL, data)


def split_ptk(ptk: bytes) -> tuple[bytes, bytes, bytes]:
    """Decompose PTK into (KCK, KEK, TK) — 16 bytes each."""
    kck = ptk[:KCK_LEN]
    kek = ptk[KCK_LEN: KCK_LEN + KEK_LEN]
    tk = ptk[KCK_LEN + KEK_LEN:]
    return kck, kek, tk


# ── MIC computation (simplified) ─────────────────────────────────────────────

def compute_mic(kck: bytes, message: bytes) -> bytes:
    """Compute a 16-byte MIC with HMAC-SHA256 (truncated to 128 bits).

    Real 802.11i uses AES-CMAC (RFC 4493) keyed by KCK.
    """
    return hmac.new(kck, message, hashlib.sha256).digest()[:MIC_LEN]


# ── GTK wrap / unwrap (simplified) ───────────────────────────────────────────

def _kek_pad(kek: bytes) -> bytes:
    """Derive a GTK_LEN-byte pad from KEK. Simulator uses HMAC-SHA256(KEK, 'GTK-wrap')."""
    return hmac.new(kek, b"GTK-wrap", hashlib.sha256).digest()[:GTK_LEN]


def wrap_gtk(kek: bytes, gtk: bytes) -> bytes:
    """Wrap GTK with KEK.  Simulator: XOR gtk with HMAC-derived pad.
    Real 802.11i uses RFC 3394 AES Key Wrap (requires AES, not in stdlib).
    """
    pad = _kek_pad(kek)
    return bytes(a ^ b for a, b in zip(gtk, pad))


def unwrap_gtk(kek: bytes, wrapped: bytes) -> bytes:
    """Unwrap GTK.  XOR is its own inverse here."""
    pad = _kek_pad(kek)
    return bytes(a ^ b for a, b in zip(wrapped, pad))


# ── dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class AccessPoint:
    """Cryptographic and association state at the AP side."""
    ssid: bytes
    bssid: bytes
    pmk: bytes
    anonce: bytes = field(default_factory=lambda: os.urandom(NONCE_LEN))
    gtk: bytes = field(default_factory=lambda: os.urandom(GTK_LEN))
    ptk: bytes = field(default_factory=lambda: b"")
    replay_counter: int = 0
    _next_aid: int = field(default=1, repr=False)

    def __post_init__(self) -> None:
        validate_ssid(self.ssid)
        validate_bssid(self.bssid)

    def alloc_aid(self) -> int:
        """Allocate the next Association ID (1–2007)."""
        if self._next_aid > 2007:
            raise RuntimeError("AID pool exhausted (max 2007 per BSS)")
        aid = self._next_aid
        self._next_aid += 1
        return aid

    def bump_replay(self) -> int:
        self.replay_counter += 1
        return self.replay_counter


@dataclass
class Station:
    """Cryptographic and association state at the STA side."""
    mac: bytes
    pmk: bytes
    snonce: bytes = field(default_factory=lambda: os.urandom(NONCE_LEN))
    ptk: bytes = field(default_factory=lambda: b"")
    gtk: bytes = field(default_factory=lambda: b"")
    aid: int = 0
    pn: int = 0   # 48-bit CCMP Packet Number, strictly monotone

    def __post_init__(self) -> None:
        validate_bssid(self.mac)  # same 6-byte unicast constraint

    def next_pn(self) -> int:
        """Increment and return PN.  A repeated PN triggers a receiver-side drop."""
        if self.pn >= PN_MAX:
            raise RuntimeError("PN overflow — full rekey required")
        self.pn += 1
        return self.pn


# ── EAPOL-Key message types ───────────────────────────────────────────────────

@dataclass(frozen=True)
class EapolKeyMsg:
    """Simplified EAPOL-Key frame (ethertype 0x888E) for simulation."""
    msg_num: int              # 1–4
    key_ack: int              # 1 → sender expects a reply
    key_mic: int              # 1 → MIC field is valid
    install: int              # 1 → receiver installs PTK
    encrypted_key_data: int   # 1 → Key Data carries wrapped GTK
    replay_counter: int
    anonce: bytes
    snonce: bytes
    mic: bytes                # MIC_LEN bytes
    key_data: bytes           # wrapped GTK or b""

    def _abbrev(self, b: bytes) -> str:
        return b[:4].hex() + "…" if b and any(b) else "(zeros)"

    def summary(self) -> str:
        flags = (
            f"KeyAck={self.key_ack} KeyMIC={self.key_mic} "
            f"Install={self.install} EncKeyData={self.encrypted_key_data}"
        )
        kd = f"  KeyData={self._abbrev(self.key_data)}" if self.key_data else ""
        return (
            f"  EAPOL-Key msg{self.msg_num}: [{flags}]  "
            f"replay_counter={self.replay_counter}\n"
            f"    ANonce={self._abbrev(self.anonce)}"
            f"  SNonce={self._abbrev(self.snonce)}"
            f"  MIC={self._abbrev(self.mic)}{kd}"
        )


# ── EAPOL 4-way handshake builders ───────────────────────────────────────────

def _msg2_payload(replay_counter: int, snonce: bytes) -> bytes:
    """Canonical payload for MIC computation in msg 2."""
    return struct.pack("!BQ", 2, replay_counter) + snonce


def _msg3_payload(replay_counter: int, anonce: bytes, wrapped_gtk: bytes) -> bytes:
    """Canonical payload for MIC computation in msg 3."""
    return struct.pack("!BQ", 3, replay_counter) + anonce + wrapped_gtk


def _msg4_payload(replay_counter: int) -> bytes:
    """Canonical payload for MIC computation in msg 4 (ACK)."""
    return struct.pack("!BQ", 4, replay_counter)


def build_msg1(ap: AccessPoint) -> EapolKeyMsg:
    """AP → STA: send ANonce.  STA can now derive PTK and generate msg 2."""
    rc = ap.bump_replay()
    return EapolKeyMsg(
        msg_num=1, key_ack=1, key_mic=0, install=0, encrypted_key_data=0,
        replay_counter=rc,
        anonce=ap.anonce,
        snonce=b"\x00" * NONCE_LEN,
        mic=b"\x00" * MIC_LEN,
        key_data=b"",
    )


def build_msg2(sta: Station, ap_bssid: bytes, msg1: EapolKeyMsg) -> EapolKeyMsg:
    """STA → AP: send SNonce + MIC(KCK, msg2_payload).

    STA derives PTK here because it now has PMK + ANonce + SNonce + MACs.
    AP verifies the MIC to confirm the STA holds the same PMK.
    """
    ptk = derive_ptk(sta.pmk, ap_bssid, sta.mac, msg1.anonce, sta.snonce)
    sta.ptk = ptk
    kck, _kek, _tk = split_ptk(ptk)
    payload = _msg2_payload(msg1.replay_counter, sta.snonce)
    mic = compute_mic(kck, payload)
    return EapolKeyMsg(
        msg_num=2, key_ack=0, key_mic=1, install=0, encrypted_key_data=0,
        replay_counter=msg1.replay_counter,
        anonce=msg1.anonce,
        snonce=sta.snonce,
        mic=mic,
        key_data=b"",
    )


def build_msg3(ap: AccessPoint, sta_mac: bytes, msg2: EapolKeyMsg) -> EapolKeyMsg:
    """AP → STA: verify msg2 MIC, derive PTK, send GTK wrapped with KEK + MIC.

    Raises ValueError if msg2 MIC is wrong (bad PSK or wrong PMK).
    GTK is bundled here — no separate group-key exchange — to halve latency.
    """
    ptk = derive_ptk(ap.pmk, ap.bssid, sta_mac, ap.anonce, msg2.snonce)
    ap.ptk = ptk
    kck, kek, _tk = split_ptk(ptk)

    # Verify msg2 MIC
    expected_mic = compute_mic(kck, _msg2_payload(msg2.replay_counter, msg2.snonce))
    if not hmac.compare_digest(expected_mic, msg2.mic):
        raise ValueError(
            "msg2 MIC mismatch — STA and AP do not share the same PMK "
            "(wrong passphrase or SSID)"
        )
    print("    [AP] msg2 MIC OK — STA knows the PMK. Deriving PTK and wrapping GTK …")

    wrapped_gtk = wrap_gtk(kek, ap.gtk)
    rc = ap.bump_replay()
    payload3 = _msg3_payload(rc, ap.anonce, wrapped_gtk)
    mic3 = compute_mic(kck, payload3)
    return EapolKeyMsg(
        msg_num=3, key_ack=1, key_mic=1, install=1, encrypted_key_data=1,
        replay_counter=rc,
        anonce=ap.anonce,
        snonce=msg2.snonce,
        mic=mic3,
        key_data=wrapped_gtk,
    )


def build_msg4(sta: Station, ap_bssid: bytes, msg3: EapolKeyMsg) -> EapolKeyMsg:
    """STA → AP: verify msg3 MIC, install PTK, unwrap GTK, send ACK MIC.

    After sending msg4, STA can immediately start sending CCMP-encrypted data.
    AP installs its PTK copy upon receiving msg4.
    """
    kck, kek, _tk = split_ptk(sta.ptk)

    # Verify msg3 MIC
    expected_mic3 = compute_mic(
        kck, _msg3_payload(msg3.replay_counter, msg3.anonce, msg3.key_data)
    )
    if not hmac.compare_digest(expected_mic3, msg3.mic):
        raise ValueError("msg3 MIC mismatch — possible rogue AP")
    print("    [STA] msg3 MIC OK — installing PTK, unwrapping GTK …")

    sta.gtk = unwrap_gtk(kek, msg3.key_data)
    payload4 = _msg4_payload(msg3.replay_counter)
    mic4 = compute_mic(kck, payload4)
    return EapolKeyMsg(
        msg_num=4, key_ack=0, key_mic=1, install=0, encrypted_key_data=0,
        replay_counter=msg3.replay_counter,
        anonce=b"\x00" * NONCE_LEN,
        snonce=b"\x00" * NONCE_LEN,
        mic=mic4,
        key_data=b"",
    )


# ── CCMP header ───────────────────────────────────────────────────────────────

def ccmp_header(pn: int, key_id: int = 0) -> bytes:
    """Build the 8-byte CCMP MPDU header (802.11i §8.3.3.2) for a given PN.

    Layout:
      Byte 0: PN0 (LSB)
      Byte 1: PN1
      Byte 2: Reserved = 0x00
      Byte 3: KeyID[7:6] | ExtIV=1[5] | Reserved[4:0]
      Bytes 4–7: PN2 … PN5 (MSB at byte 7)
    """
    if not (0 <= pn <= PN_MAX):
        raise ValueError(f"PN {pn} out of range [0, {PN_MAX}]")
    pn_b = pn.to_bytes(6, "little")       # PN0 … PN5
    return bytes([
        pn_b[0],                           # PN0
        pn_b[1],                           # PN1
        0x00,                              # Reserved
        (key_id & 0x03) << 6 | 0x20,     # KeyID | ExtIV=1
        pn_b[2],                           # PN2
        pn_b[3],                           # PN3
        pn_b[4],                           # PN4
        pn_b[5],                           # PN5
    ])


# ── pretty helpers ────────────────────────────────────────────────────────────

def _section(title: str) -> None:
    print(f"\n{'─' * 70}")
    print(f"  {title}")
    print(f"{'─' * 70}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 70)
    print("  802.11 WPA2 Association + EAPOL 4-Way Handshake Simulator")
    print("  Phase 5 · Lesson 24 · stdlib-only")
    print("=" * 70)

    # ── [1] SSID / BSSID validation ─────────────────────────────────────────
    _section("[1] SSID / BSSID Validation")

    ssid = b"CampusNet-5G"
    ap_mac = bytes.fromhex("001122aabbcc")
    sta_mac = bytes.fromhex("aabbccddeeff")

    validate_ssid(ssid)
    validate_bssid(ap_mac)
    validate_bssid(sta_mac)
    print(f"  SSID    : {ssid.decode()!r}  ({len(ssid)} bytes) — VALID")
    print(f"  AP MAC  : {_fmt_mac(ap_mac)} — VALID unicast")
    print(f"  STA MAC : {_fmt_mac(sta_mac)} — VALID unicast")

    # Edge-case rejections
    try:
        validate_ssid(b"A" * 33)
    except ValueError as exc:
        print(f"  SSID 33-byte  → rejected: {exc}")

    try:
        validate_bssid(bytes.fromhex("ff1122334455"))   # bit0=1 → multicast
    except ValueError as exc:
        print(f"  Multicast MAC → rejected: {exc}")

    # ── [2] PMK derivation ──────────────────────────────────────────────────
    _section("[2] PMK Derivation  (PBKDF2-HMAC-SHA1, 4096 iterations)")

    passphrase = "CampusSecret99"
    pmk = derive_pmk(passphrase, ssid)
    print(f"  passphrase : {passphrase!r}")
    print(f"  SSID       : {ssid!r}")
    print(f"  PMK (32 B) : {pmk.hex()}")
    print(f"  (Both AP and STA derive the same PMK independently at boot-time)")

    # ── [3] Entities ────────────────────────────────────────────────────────
    _section("[3] AP and STA Objects Initialised")

    ap = AccessPoint(ssid=ssid, bssid=ap_mac, pmk=pmk)
    sta = Station(mac=sta_mac, pmk=pmk)
    print(f"  AP  BSSID  : {_fmt_mac(ap.bssid)}")
    print(f"  AP  ANonce : {ap.anonce[:8].hex()}… (32 random bytes, generated once per assoc)")
    print(f"  AP  GTK    : {ap.gtk.hex()} (broadcast/multicast key)")
    print(f"  STA MAC    : {_fmt_mac(sta.mac)}")
    print(f"  STA SNonce : {sta.snonce[:8].hex()}… (32 random bytes)")

    # ── [4] Probe + Auth + Association ─────────────────────────────────────
    _section("[4] Association Sequence (simulated management frames)")

    print(f"  STA → AP  Probe Request   (SSID={ssid.decode()!r}, active scan)")
    print(f"  AP  → STA Probe Response  (BSSID={_fmt_mac(ap_mac)}, RSN IE, rates)")
    print(f"  STA → AP  Authentication  (Open, Algorithm=0, Transaction=1)")
    print(f"  AP  → STA Authentication  (Status=0 Success, Transaction=2)")
    print(f"  STA → AP  Assoc Request   (SSID, HT/VHT caps, RSN IE: AKM=PSK)")
    aid = ap.alloc_aid()
    sta.aid = aid
    print(f"  AP  → STA Assoc Response  (Status=0 · AID={aid})")
    print(f"  (AID {aid} is used in TIM bitmap and Block-Ack to address this STA)")

    # ── [5] EAPOL 4-way handshake ───────────────────────────────────────────
    _section("[5] EAPOL 4-Way Handshake  (ethertype 0x888E)")

    print("\n  --- Message 1: AP → STA  (ANonce) ---")
    msg1 = build_msg1(ap)
    print(msg1.summary())

    print("\n  --- Message 2: STA → AP  (SNonce + MIC) ---")
    msg2 = build_msg2(sta, ap.bssid, msg1)
    print(msg2.summary())

    print("\n  --- Message 3: AP → STA  (GTK + MIC) ---")
    msg3 = build_msg3(ap, sta.mac, msg2)
    print(msg3.summary())

    print("\n  --- Message 4: STA → AP  (ACK MIC) ---")
    msg4 = build_msg4(sta, ap.bssid, msg3)
    print(msg4.summary())

    # AP verifies msg4 and installs its PTK copy
    kck_ap, _kek_ap, _tk_ap = split_ptk(ap.ptk)
    msg4_expected = compute_mic(kck_ap, _msg4_payload(msg3.replay_counter))
    assert hmac.compare_digest(msg4_expected, msg4.mic), "AP: msg4 MIC mismatch"
    print("\n    [AP] msg4 MIC OK — PTK installed, downlink encryption ACTIVE.")

    # ── [6] Key material ────────────────────────────────────────────────────
    _section("[6] Key Material Summary")

    kck_a, kek_a, tk_a = split_ptk(ap.ptk)
    kck_s, kek_s, tk_s = split_ptk(sta.ptk)

    assert ap.ptk == sta.ptk,   "PTK mismatch — handshake error"
    assert ap.gtk == sta.gtk,   "GTK mismatch — unwrap error"

    print(f"  PTK match  : {ap.ptk == sta.ptk}  (384 bits)")
    print(f"  KCK (128b) : {kck_a.hex()}   [computes MICs on msg2/msg3/msg4]")
    print(f"  KEK (128b) : {kek_a.hex()}   [wraps GTK in msg3]")
    print(f"  TK  (128b) : {tk_a.hex()}    [feeds AES-128-CCM for data]")
    print(f"  GTK match  : {ap.gtk == sta.gtk}  (128 bits, broadcast key)")
    print(f"  GTK        : {ap.gtk.hex()}")

    # ── [7] CCMP PN replay counter ──────────────────────────────────────────
    _section("[7] CCMP Packet Number (PN) — 48-bit Replay Counter")

    print(f"  {'Frame':<8} {'PN (hex)':<16} {'CCMP header (8 bytes)'}")
    print(f"  {'-'*8} {'-'*16} {'-'*24}")
    for i in range(4):
        pn = sta.next_pn()
        hdr = ccmp_header(pn)
        print(f"  #{i + 1:<7} {pn:#016x}   {hdr.hex()}")
    print(f"  PN is strictly monotone; any duplicate or backward PN is dropped.")
    print(f"  At PN overflow ({PN_MAX:#x}) the STA must perform a full rekey.")

    # ── [8] Nine 802.11 services ────────────────────────────────────────────
    _section("[8] Nine 802.11 Services")

    services = [
        ("Distribution",     "Distribution", "Route: intra-BSS or forward across DS"),
        ("Integration",      "Distribution", "Bridge 802.11 ↔ wireline (e.g. Ethernet)"),
        ("Association",      "Distribution", f"Bind STA to AP; AP assigns AID (here: {aid})"),
        ("Reassociation",    "Distribution", "Move STA binding AP-1 → AP-2 on roam"),
        ("Disassociation",   "Distribution", "Tear down the STA-AP binding"),
        ("Authentication",   "Station",      "Verify STA identity (PSK or 802.1X)"),
        ("Deauthentication", "Station",      "Revoke authentication (forces re-auth)"),
        ("Privacy",          "Station",      "AES-128-CCM encrypt/decrypt MSDUs"),
        ("MSDU delivery",    "Station",      "Best-effort unicast/multicast delivery"),
    ]
    print(f"  {'Service':<18} {'Group':<16} {'Purpose'}")
    print(f"  {'-'*18} {'-'*15} {'-'*40}")
    for name, group, purpose in services:
        print(f"  {name:<18} {group:<16} {purpose}")

    # ── [9] Roaming latency budget ──────────────────────────────────────────
    _section("[9] Classic Roaming Latency Budget (pre-802.11r)")

    budget = [
        ("802.11k Neighbor Report req/resp",   "5–20 ms"),
        ("Reassociation Request/Response",       "5–20 ms"),
        ("EAPOL 4-way handshake (4 messages)",  "10–50 ms"),
        ("Group key handshake (optional)",       "5–20 ms"),
        ("TOTAL",                                "25–110 ms"),
    ]
    for step, t in budget:
        marker = ">>>" if step == "TOTAL" else "   "
        print(f"  {marker} {step:<42} {t}")

    print()
    print("  Amendments that cut this latency:")
    print("  • 802.11k (RRM)  — neighbor reports eliminate 200 ms of channel scanning")
    print("  • 802.11r (FT)   — pre-computed PMK-R1 per candidate AP → <10 ms total")
    print("  • 802.11v (BTM)  — AP signals STA which cell to roam to (load balance)")

    # ── [10] WPA2 vs WPA3 summary ───────────────────────────────────────────
    _section("[10] WPA2-PSK vs WPA3-SAE")

    rows = [
        ("PMK source",    "PBKDF2-SHA1(pwd, SSID, 4096)",   "Dragonfly / hunting-and-pecking KDF"),
        ("AKM suite ID",  "00-0F-AC:2 (PSK)",               "00-0F-AC:8 (SAE)"),
        ("Forward secrecy", "No — PMK fixed for lifetime of pwd", "Yes — ephemeral per session"),
        ("Dictionary risk", "Offline (capture 4-way, try PBKDF2)", "Online only (rate-limited by AP)"),
        ("4-way handshake", "Yes (PMK from PSK)", "Yes (PMK from SAE Commit/Confirm)"),
    ]
    print(f"  {'Property':<22} {'WPA2-Personal':<38} {'WPA3-Personal'}")
    print(f"  {'-'*22} {'-'*38} {'-'*38}")
    for prop, wpa2, wpa3 in rows:
        print(f"  {prop:<22} {wpa2:<38} {wpa3}")

    print()
    print("=" * 70)
    print("  Simulation complete — all MIC verifications and assertions passed.")
    print("=" * 70)


if __name__ == "__main__":
    main()
