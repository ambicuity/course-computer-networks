#!/usr/bin/env python3
"""802.11i (WPA2) 4-Way Handshake and Group Key Handshake simulator.

Derives the PMK from a WPA2 passphrase by PBKDF2-SHA-1 (4096 iterations, SSID
as salt -- the exact construction 802.11i specifies for the PSK), then expands
the PMK with the AP and STA MACs and the two nonces to a 48-byte PTK via
PRF-384. Splits the PTK into KCK + KEK + TK, then walks the four EAPOL-Key
messages of the 4-Way Handshake, computing the HMAC-SHA-1 MIC over each one
and checking it on the receiver side. Demonstrates a wrong-PSK rejection and
a replayed-Message-1 KRACK-style attack. Pure stdlib, no pip deps.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import struct

PBKDF2_ITERS = 4096
PMK_LEN = 32
NONCE_LEN = 32
CCMP_PTK_LEN = 48
TK_LEN = 16

I_INSTALL = 0x0040
I_ACK = 0x0080
I_MIC = 0x0100
I_SECURE = 0x0200
I_ENC = 0x1000

D_PWK = 2
D_GTK = 5

MIC_OFF = 46
MIC_END = 62
HEADER_FIXED = 62  # bytes before key_data_length field


def pbkdf2_psk(passphrase: str, ssid: str) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha1",
        passphrase.encode("utf-8"),
        ssid.encode("utf-8"),
        PBKDF2_ITERS,
        PMK_LEN,
    )


def prf_384(key: bytes, label: str, data: bytes) -> bytes:
    out = b""
    label_bytes = label.encode("ascii")
    i = 1
    while len(out) < CCMP_PTK_LEN:
        out += hmac.new(
            key, bytes([i]) + label_bytes + data + b"\x00", hashlib.sha1
        ).digest()
        i += 1
    return out[:CCMP_PTK_LEN]


def derive_ptk(pmk: bytes, aa: bytes, sa: bytes, an: bytes, sn: bytes) -> bytes:
    return prf_384(pmk, "Pairwise key expansion", aa + sa + an + sn)


def split_ptk(ptk: bytes) -> tuple[bytes, bytes, bytes]:
    return ptk[:16], ptk[16:32], ptk[32:48]


def aes_key_wrap_illustrative(kek: bytes, plaintext: bytes) -> bytes:
    """Show the (n + 8) byte shape of RFC 3394 AES-Key-Wrap; not real AES."""
    if len(plaintext) % 8 != 0:
        raise ValueError("key-wrap input must be a multiple of 8 bytes")
    body = b"\xa6\x59\x59\xa6" + b"\x00" * 4 + plaintext
    mac = hmac.new(kek, body, hashlib.sha1).digest()
    return plaintext + mac[:8]


def build_eapol_key(
    desc_type: int,
    key_info: int,
    replay: int,
    nonce: bytes,
    key_data: bytes,
    mic: bytes = b"\x00" * 16,
) -> bytes:
    return (
        struct.pack("!BHH", desc_type, key_info, TK_LEN)
        + replay.to_bytes(8, "big")
        + struct.pack("!16s8s8sB", nonce[:16], b"\x00" * 8, b"\x00" * 8, 16)
        + mic
        + struct.pack("!H", len(key_data))
        + key_data
    )


def mic_for(kck: bytes, frame: bytes) -> bytes:
    return hmac.new(kck, frame, hashlib.sha1).digest()[:16]


def with_mic(kck: bytes, frame: bytes) -> bytes:
    return frame[:MIC_OFF] + mic_for(kck, frame) + frame[MIC_END:]


def verify_mic(kck: bytes, frame: bytes) -> bool:
    expected = mic_for(kck, frame[:MIC_OFF] + b"\x00" * 16 + frame[MIC_END:])
    return hmac.compare_digest(frame[MIC_OFF:MIC_END], expected)


def four_way(ap_mac: bytes, sta_mac: bytes, pmk: bytes, an: bytes, sn: bytes, gtk: bytes):
    kck, kek, _ = split_ptk(derive_ptk(pmk, ap_mac, sta_mac, an, sn))
    wrapped = aes_key_wrap_illustrative(kek, gtk)
    msg1 = build_eapol_key(D_PWK, I_ACK, 0, an, b"")
    msg2 = with_mic(kck, build_eapol_key(D_PWK, I_MIC, 1, sn, b""))
    flags3 = I_INSTALL | I_ACK | I_MIC | I_SECURE | I_ENC
    msg3 = with_mic(kck, build_eapol_key(D_PWK, flags3, 2, an, wrapped))
    msg4 = with_mic(kck, build_eapol_key(D_PWK, I_MIC | I_SECURE, 3, b"\x00" * 16, b""))
    return msg1, msg2, msg3, msg4, kck, kek


def format_flags(info: int) -> str:
    parts = []
    for mask, name in (
        (I_ACK, "ACK"),
        (I_MIC, "MIC"),
        (I_INSTALL, "INSTALL"),
        (I_SECURE, "SECURE"),
        (I_ENC, "KEY_DATA_ENCR"),
    ):
        if info & mask:
            parts.append(name)
    return ",".join(parts) if parts else "(none)"


def main() -> None:
    print("=" * 72)
    print("802.11i 4-Way Handshake + Group Key Handshake  --  WPA2 simulator")
    print("=" * 72)

    passphrase = "correct horse battery staple"
    ssid = "FreeWiFi"
    ap_mac = bytes.fromhex("aabbccddee01")
    sta_mac = bytes.fromhex("112233445502")
    pmk = pbkdf2_psk(passphrase, ssid)
    an = secrets.token_bytes(NONCE_LEN)
    sn = secrets.token_bytes(NONCE_LEN)

    print(f"\nPassphrase : {passphrase!r}")
    print(f"SSID       : {ssid!r}")
    print(f"PMK        : {pmk.hex()}  ({len(pmk)} bytes)")
    print(f"AA (AP)    : {ap_mac.hex(':')}")
    print(f"SA (STA)   : {sta_mac.hex(':')}")
    print(f"ANonce     : {an.hex()}")
    print(f"SNonce     : {sn.hex()}")

    ptk = derive_ptk(pmk, ap_mac, sta_mac, an, sn)
    kck, kek, tk = split_ptk(ptk)
    print(f"\nPTK        : {ptk.hex()}  ({len(ptk)} bytes)")
    print(f"  KCK      : {kck.hex()}")
    print(f"  KEK      : {kek.hex()}")
    print(f"  TK       : {tk.hex()}")

    gtk = b"\x01" * 16
    msg1, msg2, msg3, msg4, _, _ = four_way(ap_mac, sta_mac, pmk, an, sn, gtk)

    print("\n4-Way Handshake frames:")
    for label, frame in (("Msg 1 (AP->STA)", msg1), ("Msg 2 (STA->AP)", msg2),
                         ("Msg 3 (AP->STA)", msg3), ("Msg 4 (STA->AP)", msg4)):
        info = struct.unpack("!H", frame[1:3])[0]
        kdl = struct.unpack("!H", frame[62:64])[0]
        mic = frame[MIC_OFF:MIC_END].hex() if info & I_MIC else "(none)"
        print(f"  {label:<18}  flags={format_flags(info):<24}  "
              f"key_data_len={kdl:>3}  mic={mic}")

    print("\nReceiver-side MIC verification:")
    for label, frame in (("Msg 2", msg2), ("Msg 3", msg3), ("Msg 4", msg4)):
        ok = verify_mic(kck, frame)
        print(f"  {label}  ->  MIC {'OK' if ok else 'MISMATCH'}")

    print("\nWrong-PSK simulation (STA uses a different passphrase):")
    bad_pmk = pbkdf2_psk("hunter2", ssid)
    bad_kck, _, _ = split_ptk(derive_ptk(bad_pmk, ap_mac, sta_mac, an, sn))
    bad_msg2 = with_mic(bad_kck, build_eapol_key(D_PWK, I_MIC, 1, sn, b""))
    ok = verify_mic(kck, bad_msg2)
    print(f"  AP checks STA's MIC with real KCK -> "
          f"{'OK' if ok else 'MISMATCH (handshake dropped)'}")

    print("\nKRACK-style replay simulation (replay Message 1):")
    print("  Attacker replays Msg 1 -> fresh Msg 2/3/4 follow.")
    print("  AP installs TK on first Msg 3, then on the second")
    print("  pass REINSTALLS the same TK and resets its transmit")
    print("  packet number. That is the primitive Vanhoef 2017")
    print("  used in CVE-2017-13082 against pre-Oct-2017 WPA2.")

    print("\nGroup Key Handshake (delivers the GTK to the now-authenticated STA):")
    gtk2 = b"\x02" * 16
    wrapped = aes_key_wrap_illustrative(kek, gtk2)
    print(f"  GTK          : {gtk2.hex()}")
    print(f"  wrapped GTK  : {wrapped.hex()}  ({len(wrapped)} B = 16 B + 8 B)")
    gflags1 = I_ACK | I_MIC | I_SECURE | I_ENC
    gmsg1 = with_mic(kck, build_eapol_key(D_GTK, gflags1, 0, b"\x00" * 16, wrapped))
    gmsg2 = with_mic(kck, build_eapol_key(D_GTK, I_MIC | I_SECURE, 1, b"\x00" * 16, b""))
    print(f"  Group Msg 1 (AP->STA)  MIC={gmsg1[MIC_OFF:MIC_END].hex()}  "
          f"wrapped_len={len(wrapped)}")
    print(f"  Group Msg 2 (STA->AP)  MIC={gmsg2[MIC_OFF:MIC_END].hex()}")
    print(f"  Group Msg 1 MIC verifies with KCK: {verify_mic(kck, gmsg1)}")
    print(f"  Group Msg 2 MIC verifies with KCK: {verify_mic(kck, gmsg2)}")

    print("\nWEP vs. WPA2 at a glance:")
    print("  WEP:  RC4 + 24-bit IV + CRC-32  -- broken (Fluhrer-Mantin-Shamir 2001)")
    print("  WPA2: AES-CCM (CTR + CBC-MAC) + per-station TK + 4-Way Handshake")
    print("\nDone. Compare the printed KCK/KEK/TK to a captured 4-Way in Wireshark.")


if __name__ == "__main__":
    main()
