"""Wireless security: WPA2 four-packet handshake and WEP weakness demo.

Simulates the 802.11i (WPA2) key-derivation handshake, CCMP
encryption/decryption flow, and demonstrates WEP's fatal keystream
reuse flaw. stdlib-only, educational — no real crypto.
"""

from __future__ import annotations
import hashlib
import hmac
import os
import random
from dataclasses import dataclass
from typing import Optional


def random_bytes(n: int) -> bytes:
    return bytes(random.randint(0, 255) for _ in range(n))


def sha1_hmac(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha1).digest()


def derive_session_key(master_key: bytes, nonce_ap: bytes,
                       nonce_client: bytes, mac_ap: bytes,
                       mac_client: bytes) -> bytes:
    """Derive a session key from nonces, MAC addresses, and master key."""
    material = master_key + nonce_ap + nonce_client + mac_ap + mac_client
    return hashlib.sha256(material).digest()[:16]  # 128-bit session key


@dataclass
class HandshakeMessage:
    step: int
    direction: str
    content: bytes
    mic: Optional[bytes] = None


def simulate_handshake(master_key: bytes, mac_ap: bytes,
                       mac_client: bytes) -> tuple[bytes, list[HandshakeMessage]]:
    """Run the four-packet WPA2 handshake."""
    messages: list[HandshakeMessage] = []

    # Message 1: AP -> Client (AP's nonce)
    nonce_ap = random_bytes(16)
    msg1 = HandshakeMessage(1, "AP -> Client", nonce_ap)
    messages.append(msg1)
    print(f"  Step 1 [AP -> Client]: nonce_ap = {nonce_ap.hex()[:16]}...")

    # Message 2: Client -> AP (client nonce + MIC)
    nonce_client = random_bytes(16)
    session_key = derive_session_key(master_key, nonce_ap, nonce_client,
                                       mac_ap, mac_client)
    mic2 = sha1_hmac(session_key, nonce_client + mac_client)[:8]
    msg2 = HandshakeMessage(2, "Client -> AP", nonce_client + mac_client, mic2)
    messages.append(msg2)
    print(f"  Step 2 [Client -> AP]: nonce_c = {nonce_client.hex()[:16]}...")
    print(f"    MIC = {mic2.hex()}")

    # AP computes the same session key
    ap_key = derive_session_key(master_key, nonce_ap, nonce_client,
                                  mac_ap, mac_client)
    assert ap_key == session_key, "Key derivation mismatch!"
    print(f"  [AP derives same session key: {session_key.hex()[:16]}...]")

    # Message 3: AP -> Client (group key + MIC)
    group_key = random_bytes(16)
    mic3 = sha1_hmac(session_key, group_key)[:8]
    msg3 = HandshakeMessage(3, "AP -> Client", group_key, mic3)
    messages.append(msg3)
    print(f"  Step 3 [AP -> Client]: group_key = {group_key.hex()[:16]}...")
    print(f"    MIC = {mic3.hex()}")

    # Message 4: Client -> AP (acknowledgment + MIC)
    ack = b"ACK"
    mic4 = sha1_hmac(session_key, ack)[:8]
    msg4 = HandshakeMessage(4, "Client -> AP", ack, mic4)
    messages.append(msg4)
    print(f"  Step 4 [Client -> AP]: ACK, MIC = {mic4.hex()}")

    return session_key, messages


def simulate_ccmp(session_key: bytes, plaintext: bytes) -> dict:
    """Simulate CCMP: AES counter mode encryption + CBC-MAC integrity."""
    # Counter mode (simulated — no real AES, just XOR with key-derived stream)
    counter = 0
    ciphertext = bytearray()
    for i in range(0, len(plaintext), 16):
        block = plaintext[i:i + 16]
        ctr_block = sha1_hmac(session_key, counter.to_bytes(8, "big"))
        ctr_block = ctr_block[:len(block)]
        ct_block = bytes(b ^ k for b, k in zip(block, ctr_block))
        ciphertext.extend(ct_block)
        counter += 1

    # CBC-MAC (simulated)
    mac_chain = b"\x00" * 16
    for i in range(0, len(plaintext), 16):
        block = plaintext[i:i + 16].ljust(16, b"\x00")
        mixed = bytes(a ^ b for a, b in zip(block, mac_chain))
        mac_chain = sha1_hmac(session_key, mixed)[:16]

    return {
        "ciphertext": bytes(ciphertext),
        "mic": mac_chain,
        "counter_blocks": counter,
    }


def simulate_wep_crack() -> None:
    """Demonstrate WEP's keystream reuse flaw."""
    print("\n[WEP Keystream Reuse Flaw]\n")
    key = random_bytes(3)  # WEP used 24-bit IV + 40-bit key
    iv1 = b"\x01\x00\x00"
    iv2 = b"\x01\x00\x00"  # same IV -> same keystream

    def wep_keystream(iv: bytes, key: bytes) -> bytes:
        return hashlib.sha1(iv + key).digest()[:16]

    ks1 = wep_keystream(iv1, key)
    ks2 = wep_keystream(iv2, key)

    msg_a = b"Hello, World!!!"
    msg_b = b"Attack at dawn"

    ct_a = bytes(m ^ k for m, k in zip(msg_a, ks1))
    ct_b = bytes(m ^ k for m, k in zip(msg_b, ks2))

    print(f"  IV1 = IV2 = {iv1.hex()} -> SAME keystream")
    print(f"  Ciphertext A: {ct_a.hex()}")
    print(f"  Ciphertext B: {ct_b.hex()}")
    xor_ct = bytes(a ^ b for a, b in zip(ct_a, ct_b))
    xor_pt = bytes(a ^ b for a, b in zip(msg_a, msg_b))
    print(f"  CT_A XOR CT_B = {xor_ct.hex()}")
    print(f"  PT_A XOR PT_B = {xor_pt.hex()}")
    print(f"  MATCH: {xor_ct == xor_pt}")
    print("  -> Attacker XORs two ciphertexts to get XOR of two plaintexts.")
    print("  -> With known plaintext (e.g., predictable IP header), the")
    print("     keystream is recovered and all other ciphertexts decrypt.")


def simulate_bluetooth() -> None:
    """Demonstrate Bluetooth passkey weakness."""
    print("\n[Bluetooth Passkey Weakness]\n")
    old_choices = 10 ** 4   # 4 digits
    new_choices = 10 ** 6   # 6 digits
    print(f"  Pre-2.1 passkey: 4 digits = {old_choices} choices")
    print(f"  2.1+ passkey:    6 digits = {new_choices} choices")
    print(f"  Common default: '1234' or '0000'")
    print(f"  Brute-force 4-digit at 100/s: {old_choices // 100}s")
    print(f"  Brute-force 6-digit at 100/s: {new_choices // 100}s")
    print("  Bluetooth authenticates devices, not users.")
    print("  Device theft grants account access.")


def main() -> None:
    print("=" * 72)
    print("Wireless Security: WPA2 Handshake and WEP Weakness")
    print("=" * 72)

    random.seed(42)

    # --- WPA2 four-packet handshake ---
    print("\n[WPA2 Four-Packet Handshake]\n")
    master_key = random_bytes(16)
    mac_ap = bytes([0x00, 0x1A, 0x2B, 0x3C, 0x4D, 0x5E])
    mac_client = bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])
    session_key, msgs = simulate_handshake(master_key, mac_ap, mac_client)
    print(f"\n  Session key established: {session_key.hex()[:16]}...")
    print(f"  Handshake complete: {len(msgs)} messages exchanged")

    # --- CCMP encryption ---
    print("\n[CCMP: AES-128 Counter Mode + CBC-MAC]\n")
    plaintext = b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
    result = simulate_ccmp(session_key, plaintext)
    print(f"  Plaintext ({len(plaintext)}B): {plaintext[:30]}...")
    print(f"  Ciphertext:  {result['ciphertext'][:16].hex()}...")
    print(f"  MIC:         {result['mic'].hex()[:16]}...")
    print(f"  Counter blocks used: {result['counter_blocks']}")

    # --- Shared-password weakness ---
    print("\n[Shared-Password Scenario (Home WPA2)]\n")
    print("  Password: 'myhomepassword'")
    pwd = b"myhomepassword"
    k_a = derive_session_key(pwd, random_bytes(16), random_bytes(16),
                              mac_ap, bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06]))
    k_b = derive_session_key(pwd, random_bytes(16), random_bytes(16),
                              mac_ap, bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x07]))
    print(f"  Client A session key: {k_a.hex()[:16]}...")
    print(f"  Client B session key: {k_b.hex()[:16]}...")
    print("  With the shared password, Client A can derive Client B's key")
    print("  because all clients have the same password.")

    # --- WEP crack ---
    simulate_wep_crack()

    # --- Bluetooth ---
    simulate_bluetooth()

    # --- Summary ---
    print("\n" + "=" * 72)
    print("Summary:")
    print("  WEP: broken (weak keying, CRC integrity, keystream reuse)")
    print("  WPA2/CCMP: real security (four-packet handshake, AES-128)")
    print("  Home WPA2: shared password lets clients derive each other's keys")
    print("  Bluetooth: device auth (not user), weak passkeys, E0 concerns")
    print("=" * 72)


if __name__ == "__main__":
    main()
