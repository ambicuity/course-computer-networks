#!/usr/bin/env python3
"""TLS 1.2 (RFC 5246) Handshake and Record Protocol simulator.

Walks the seven TLS 1.2 handshake messages: ClientHello, ServerHello,
Certificate, ServerHelloDone, ClientKeyExchange, ChangeCipherSpec,
Finished. Derives the 48-byte master secret from the premaster secret
via the TLS 1.2 PRF (HMAC-SHA-256), then expands it into the 104-byte
key block for AES-128-CBC + HMAC-SHA-1, splitting into the six
client/server MAC + key + IV values. Builds a synthetic HTTP request,
computes the MAC-then-encrypt path of the Record Protocol, and shows
the 5-byte record header + ciphertext. Also runs a TLS 1.3 (RFC 8446)
comparison: one round trip, AEAD tag replaces the explicit MAC, and
the static-RSA key transport is removed. Pure stdlib, no pip deps.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import struct

TLS_MAJOR = 3
TLS_1_2 = 0x0303
TLS_1_3 = 0x0304
SSL_3_0 = 0x0300

CT_CHANGE_CIPHER_SPEC = 20
CT_ALERT = 21
CT_HANDSHAKE = 22
CT_APPDATA = 23

HS_CLIENT_HELLO = 1
HS_SERVER_HELLO = 2
HS_CERTIFICATE = 11
HS_SERVER_HELLO_DONE = 14
HS_CLIENT_KEY_EXCHANGE = 16
HS_FINISHED = 20

CIPHER_AES128_CBC_SHA = bytes.fromhex("002F")
PMS_LEN = 48
MS_LEN = 48
KB_LEN = 104
KEY_LEN = 16
MAC_LEN = 20
IV_LEN = 16
RECORD_MAX = 16384


def p_hash(secret: bytes, seed: bytes, length: int) -> bytes:
    out = b""
    a = seed
    while len(out) < length:
        a = hmac.new(secret, a, hashlib.sha256).digest()
        out += hmac.new(secret, a + seed, hashlib.sha256).digest()
    return out[:length]


def prf_tls12(secret: bytes, label: str, seed: bytes, length: int) -> bytes:
    return p_hash(secret, label.encode("ascii") + seed, length)


def derive_master_secret(premaster: bytes, r_client: bytes, r_server: bytes) -> bytes:
    return prf_tls12(premaster, "master secret", r_client + r_server, MS_LEN)


def derive_key_block(master: bytes, r_client: bytes, r_server: bytes) -> bytes:
    return prf_tls12(master, "key expansion", r_server + r_client, KB_LEN)


def split_key_block(block: bytes) -> dict[str, bytes]:
    return {
        "client_write_MAC_key": block[0:20],
        "server_write_MAC_key": block[20:40],
        "client_write_key": block[40:56],
        "server_write_key": block[56:72],
        "client_write_IV": block[72:88],
        "server_write_IV": block[88:104],
    }


def make_record(content_type: int, version: int, payload: bytes) -> bytes:
    return struct.pack("!BHH", content_type, version, len(payload)) + payload


def make_handshake(msg_type: int, body: bytes) -> bytes:
    return struct.pack("!B", msg_type) + struct.pack("!I", len(body))[1:] + body


def illustrative_aes_cbc_enc(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    out = bytearray()
    prev = iv
    for off in range(0, len(plaintext), 16):
        block = plaintext[off : off + 16].ljust(16, b"\x00")
        ks = hmac.new(key, prev, hashlib.sha256).digest()[:16]
        out.extend(bytes(a ^ b ^ c for a, b, c in zip(block, ks, prev)))
        prev = bytes(out[off : off + 16])
    return bytes(out)


def record_mac_then_encrypt(
    seq: int,
    content_type: int,
    version: int,
    plaintext: bytes,
    mac_key: bytes,
    enc_key: bytes,
    iv: bytes,
) -> bytes:
    seq_bytes = seq.to_bytes(8, "big")
    mac_input = seq_bytes + struct.pack("!BHH", content_type, version, len(plaintext)) + plaintext
    mac = hmac.new(mac_key, mac_input, hashlib.sha1).digest()
    padded = plaintext + mac
    pad_len = 16 - (len(padded) % 16)
    padded += bytes([pad_len]) * pad_len
    cipher = illustrative_aes_cbc_enc(padded, enc_key, iv)
    return make_record(content_type, version, cipher)


def run_tls12(r_client: bytes, r_server: bytes, premaster: bytes, server_cert_der: bytes) -> dict:
    master = derive_master_secret(premaster, r_client, r_server)
    block = derive_key_block(master, r_client, r_server)
    keys = split_key_block(block)
    client_hello = r_client + b"\x00" * 32 + CIPHER_AES128_CBC_SHA + b"\x00"
    server_hello = r_server + CIPHER_AES128_CBC_SHA + b"\x00"
    client_ke = struct.pack("!H", TLS_1_2) + premaster[2:]
    cert_body = struct.pack("!I", len(server_cert_der))[1:] + server_cert_der
    transcript = (
        make_handshake(HS_CLIENT_HELLO, client_hello)
        + make_handshake(HS_SERVER_HELLO, server_hello)
        + make_handshake(HS_CERTIFICATE, cert_body)
        + make_handshake(HS_SERVER_HELLO_DONE, b"")
        + make_handshake(HS_CLIENT_KEY_EXCHANGE, client_ke)
    )
    verify_client = prf_tls12(master, "client finished", hashlib.sha256(transcript).digest(), 12)
    http = b"GET /index.html HTTP/1.1\r\nHost: bank.example.com\r\n\r\n"
    record = record_mac_then_encrypt(
        seq=0, content_type=CT_APPDATA, version=TLS_1_2, plaintext=http,
        mac_key=keys["client_write_MAC_key"], enc_key=keys["client_write_key"],
        iv=keys["client_write_IV"],
    )
    return {"master": master, "key_block": block, "keys": keys,
            "verify_client": verify_client, "http_record": record}


def run_tls13(r_client: bytes, r_server: bytes, shared: bytes) -> dict:
    hs_secret = hmac.new(b"\x00" * 32, shared + b"\x00", hashlib.sha256).digest()
    c_hs = prf_tls12(hs_secret, "c hs traffic", r_client + r_server, 32)
    finished_key_c = hmac.new(c_hs, b"", hashlib.sha256).digest()[:32]
    return {"handshake_secret": hs_secret,
            "client_handshake_traffic_secret": c_hs,
            "client_finished_key": finished_key_c}


def main() -> None:
    print("=" * 72)
    print("TLS 1.2 Handshake + Record Protocol  --  simulator (RFC 5246)")
    print("=" * 72)

    r_client = secrets.token_bytes(32)
    r_server = secrets.token_bytes(32)
    premaster = struct.pack("!H", TLS_1_2) + secrets.token_bytes(PMS_LEN - 2)
    server_cert_der = b"\x30\x82" + struct.pack("!H", 1024) + b"\x00" * 1022

    print(f"\nR_A (client random) : {r_client.hex()}")
    print(f"R_B (server random) : {r_server.hex()}")
    print(f"Premaster secret P  : {premaster.hex()}  ({len(premaster)} bytes)")
    print(f"  first 2 bytes (version) = {premaster[:2].hex()} (TLS 1.2 = 0303)")

    state = run_tls12(r_client, r_server, premaster, server_cert_der)

    print(f"\nMaster secret       : {state['master'].hex()}  ({len(state['master'])} bytes)")
    print(f"Key block           : {state['key_block'].hex()}  ({len(state['key_block'])} bytes)")

    print("\nKey block split (AES-128-CBC + HMAC-SHA-1 = 104 B):")
    for name, value in state["keys"].items():
        print(f"  {name:<24}: {value.hex()}  ({len(value)} B)")

    print("\nHandshake messages (each wrapped in a record header):")
    msgs = [
        ("1 ClientHello       C->S", HS_CLIENT_HELLO, r_client + b"\x00" * 32 + CIPHER_AES128_CBC_SHA + b"\x00"),
        ("2 ServerHello       S->C", HS_SERVER_HELLO, r_server + CIPHER_AES128_CBC_SHA + b"\x00"),
        ("3 Certificate       S->C", HS_CERTIFICATE, struct.pack("!I", len(server_cert_der))[1:] + server_cert_der),
        ("4 ServerHelloDone   S->C", HS_SERVER_HELLO_DONE, b""),
        ("5 ClientKeyExchange C->S", HS_CLIENT_KEY_EXCHANGE, struct.pack("!H", TLS_1_2) + premaster[2:]),
        ("7 Finished          C->S", HS_FINISHED, state["verify_client"]),
    ]
    for label, mtype, body in msgs:
        hs = make_handshake(mtype, body)
        rec = make_record(CT_HANDSHAKE, TLS_1_2, hs)
        print(f"  {label}  rec_len={len(rec)}  hs_len={len(hs)}")
    print(f"  6 ChangeCipherSpec C->S  rec_len=6  payload=01")

    print(f"\nverify_data (client) : {state['verify_client'].hex()}  ({len(state['verify_client'])} B)")

    print("\nRecord Protocol (MAC-then-encrypt) on a synthetic HTTP request:")
    rec = state["http_record"]
    print(f"  rec header: type={rec[0]:02x} version={rec[1]:02x}{rec[2]:02x} "
          f"length={(rec[3] << 8) | rec[4]}  cipher={len(rec) - 5} B")

    print("\nTLS 1.3 comparison (RFC 8446):")
    t13 = run_tls13(r_client, r_server, secrets.token_bytes(32))
    print(f"  handshake_secret       : {t13['handshake_secret'].hex()[:32]}...  (32 B)")
    print(f"  client hs traffic sec  : {t13['client_handshake_traffic_secret'].hex()}")
    print(f"  client finished key    : {t13['client_finished_key'].hex()[:32]}...")
    print("  - one round trip (vs. two in TLS 1.2)")
    print("  - AEAD-only (AES-GCM / ChaCha20-Poly1305 / AES-CCM)")
    print("  - static RSA key transport REMOVED (DHE/ECDHE only)")
    print("  - 0-RTT data possible on resumption")

    print("\nDowngrade simulation (force SSL 3.0):")
    print("  With TLS 1.2 verify_data still verifies the transcript -- this is")
    print("  why TLS 1.3 added a sentinel in the last 8 bytes of ServerHello.random")
    print("  (tls13_downgrade) that detects a TLS-1.3-capable client being demoted.")

    print("\nDone. Compare the master secret to a 'CLIENT_RANDOM' line in keylog.txt.")


if __name__ == "__main__":
    main()
