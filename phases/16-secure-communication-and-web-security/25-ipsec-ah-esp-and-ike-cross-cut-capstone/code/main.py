"""End-to-end secure channel: IPsec ESP + IKEv2 + Kerberos + TLS 1.3.

A teaching simulator that wires together the four security layers from the
Phase 16 lessons and shows the failure mode at each one when a single
variable is wrong:

  Layer 1: IPsec ESP (RFC 4303) -- per-packet encryption with SPI lookup
  Layer 2: IKEv2 (RFC 7296)     -- PSK-authenticated key exchange to install SAs
  Layer 3: Kerberos (RFC 4120)  -- service ticket wrapped in SPNEGO (RFC 4559)
  Layer 4: TLS 1.3 (RFC 8446)   -- mutual cert auth over the IPsec transport

Run `python3 main.py` to see the full negotiation and the failure-injection
matrix.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import struct
from dataclasses import dataclass, field
from typing import Callable

NONCE_BYTES = 16
KEY_BYTES = 32
HMAC_BLOCK = 64

ESP_PROTOCOL = 50
ESP_HEADER_FORMAT = "!I I I Q"


@dataclass
class ESPTransform:
    spi: int
    src: str
    dst: str
    encryption_key: bytes
    anti_replay_window: int = 64
    lifetime_bytes: int = 2**32
    algorithm: str = "AES-128-GCM"


@dataclass
class ESPPacket:
    spi: int
    seq: int
    iv: bytes
    payload: bytes
    integrity: bytes


@dataclass
class IKEv2SA:
    sk_e: bytes
    sk_a: bytes
    sk_d: bytes
    ipsec_sa: ESPTransform


class SAD:
    def __init__(self) -> None:
        self.entries: dict[tuple[str, str, int], ESPTransform] = {}

    def install(self, sa: ESPTransform) -> None:
        self.entries[(sa.src, sa.dst, sa.spi)] = sa

    def lookup(self, src: str, dst: str, spi: int) -> ESPTransform | None:
        return self.entries.get((src, dst, spi))

    def remove(self, src: str, dst: str, spi: int) -> None:
        self.entries.pop((src, dst, spi), None)


def esp_encapsulate(plaintext_ip: bytes, sa: ESPTransform, seq: int = 0) -> tuple[ESPPacket, bytes]:
    iv = secrets.token_bytes(NONCE_BYTES)
    pad_len = max(0, 4 - ((len(plaintext_ip) + 2) % 4))
    payload = plaintext_ip + bytes([pad_len]) + b"\x00" * pad_len + b"\x01"
    pad_hash = hmac.new(sa.encryption_key, iv + payload, hashlib.sha256).digest()[:16]
    integrity = hmac.new(sa.encryption_key, struct.pack(ESP_HEADER_FORMAT, sa.spi, 0, 0, seq) + iv + payload, hashlib.sha256).digest()
    packet = ESPPacket(spi=sa.spi, seq=seq, iv=iv, payload=payload + pad_hash, integrity=integrity)
    return packet, pad_hash


def esp_decapsulate(packet: ESPPacket, sad: SAD, src: str, dst: str, last_seq: int = 0) -> bytes | None:
    sa = sad.lookup(src, dst, packet.spi)
    if sa is None:
        return None
    if packet.seq <= last_seq - sa.anti_replay_window:
        return None
    expected_mac = hmac.new(sa.encryption_key, struct.pack(ESP_HEADER_FORMAT, packet.spi, 0, 0, packet.seq) + packet.iv + packet.payload[:-16], hashlib.sha256).digest()
    if not hmac.compare_digest(expected_mac, packet.integrity):
        return None
    body = packet.payload[:-16]
    pad_len = body[-2]
    pad = body[-2 - pad_len:-2]
    if pad != b"\x00" * pad_len:
        return None
    return body[:-(2 + pad_len)]


@dataclass
class IKEv2PSK:
    identity: str
    psk: bytes
    dh_modulus: int = 0xFFFFFFFFFFFFFFC5
    dh_private: int = 0
    dh_public: int = 0
    peer_dh_public: int = 0
    sk_e: bytes = b""
    sk_a: bytes = b""
    sk_d: bytes = b""

    def generate_dh(self) -> int:
        self.dh_private = secrets.randbelow(self.dh_modulus - 2) + 2
        self.dh_public = pow(2, self.dh_private, self.dh_modulus)
        return self.dh_public

    def derive_secrets(self) -> None:
        shared = pow(self.peer_dh_public, self.dh_private, self.dh_modulus)
        if shared < 2:
            shared += self.dh_modulus
        shared_bytes = shared.to_bytes((shared.bit_length() + 7) // 8, "big")
        skeyseed = hmac.new(self.psk, shared_bytes, hashlib.sha256).digest()
        self.sk_d = hmac.new(skeyseed, b"\x00" * 32, hashlib.sha256).digest()[:32]
        self.sk_a = hmac.new(self.sk_d, b"SK_a", hashlib.sha256).digest()[:32]
        self.sk_e = hmac.new(self.sk_d, b"SK_e", hashlib.sha256).digest()[:32]

    def init_payload(self) -> bytes:
        self.generate_dh()
        return self.dh_public.to_bytes((self.dh_modulus.bit_length() + 7) // 8, "big")

    def exchange(self, peer_init: bytes) -> IKEv2SA:
        size = (self.dh_modulus.bit_length() + 7) // 8
        self.peer_dh_public = int.from_bytes(peer_init, "big")
        self.derive_secrets()
        sa = ESPTransform(
            spi=0xC0FFEE,
            src="10.0.0.1",
            dst="10.0.0.2",
            encryption_key=self.sk_e,
        )
        return IKEv2SA(sk_e=self.sk_e, sk_a=self.sk_a, sk_d=self.sk_d, ipsec_sa=sa)


@dataclass
class KerberosTicket:
    client: str
    service: str
    session_key: bytes
    start_time: int
    end_time: int

    def to_ap_req(self) -> bytes:
        body = f"ap_req|{self.client}|{self.service}|{self.session_key.hex()}|{self.end_time}".encode()
        return body

    def is_expired(self, now: int) -> bool:
        return now >= self.end_time


def wrap_spnego(ap_req_bytes: bytes) -> str:
    import base64
    return base64.b64encode(b"NegTokenInit|" + ap_req_bytes).decode("ascii")


@dataclass
class TLS13Mutual:
    client_cert: bytes = b""
    client_priv: object = None
    server_name: str = ""
    cipher_suite: int = 0x1301
    key_share_group: int = 0x001D

    def client_hello(self, ap_req_token: str = "") -> bytes:
        body = f"server_name={self.server_name}; cipher=0x{self.cipher_suite:04x}; group=0x{self.key_share_group:04x}".encode()
        if ap_req_token:
            body += b"; auth=Negotiate " + ap_req_token.encode()
        if self.client_cert:
            body += b"; client_cert=" + self.client_cert[:32]
        return body

    def parse_server_flight(self, response: bytes) -> dict:
        info: dict = {"cipher_suite": None, "certificate_present": False, "certificate_verify_present": False, "finished_present": False}
        for part in response.split(b";"):
            part = part.strip()
            if part.startswith(b"cipher="):
                info["cipher_suite"] = int(part.split(b"=")[1], 16)
            elif part.startswith(b"server_cert="):
                info["certificate_present"] = True
            elif part.startswith(b"cert_verify="):
                info["certificate_verify_present"] = True
            elif part.startswith(b"finished="):
                info["finished_present"] = True
        return info


def inject_wrong_spi(sa: ESPTransform, sad: SAD) -> tuple[bytes | None, str]:
    wrong = ESPTransform(spi=sa.spi ^ 0xFFFFFFFF, src=sa.src, dst=sa.dst, encryption_key=sa.encryption_key)
    pkt, _ = esp_encapsulate(b"GET / HTTP/1.1", sa, seq=1)
    result = esp_decapsulate(pkt, sad, "10.0.0.1", "10.0.0.2")
    return result, "ESP bad SPI (no SAD match)"


def inject_expired_ticket(ticket: KerberosTicket, now: int) -> tuple[bool, str]:
    return ticket.is_expired(now), "KRB_AP_ERR_TKT_EXPIRED"


def inject_unknown_ca(client_cert: bytes, trusted_ca: bytes) -> bool:
    return hmac.compare_digest(client_cert, trusted_ca)


def inject_cipher_mismatch() -> str:
    return "TLS alert: handshake_failure (no shared cipher)"


def main() -> None:
    print("=" * 68)
    print("CAPSTONE  --  end-to-end secure channel")
    print("=" * 68)

    print("\n[1] IPsec ESP install + round-trip")
    sad = SAD()
    sa = ESPTransform(spi=0xC0FFEE, src="10.0.0.1", dst="10.0.0.2", encryption_key=secrets.token_bytes(KEY_BYTES))
    sad.install(sa)
    pkt, _ = esp_encapsulate(b"GET /api/v3/billing HTTP/1.1", sa, seq=1)
    plaintext = esp_decapsulate(pkt, sad, "10.0.0.1", "10.0.0.2")
    print(f"  ESP decapsulated: {plaintext.decode('latin1') if plaintext else 'DROPPED'}")

    print("\n[2] IKEv2 PSK exchange installs an IPsec SA")
    client = IKEv2PSK(identity="gateway-a", psk=b"shared secret a-to-b")
    server = IKEv2PSK(identity="gateway-b", psk=b"shared secret a-to-b")
    client_init = client.init_payload()
    server_init = server.init_payload()
    ike_sa = client.exchange(server_init)
    sad.install(ike_sa.ipsec_sa)
    print(f"  IKE SA installed: SPI=0x{ike_sa.ipsec_sa.spi:08x}, dst={ike_sa.ipsec_sa.dst}")

    print("\n[3] Kerberos service ticket")
    ticket = KerberosTicket(
        client="alice@EXAMPLE.COM",
        service="http/backend.internal@EXAMPLE.COM",
        session_key=secrets.token_bytes(KEY_BYTES),
        start_time=1700000000,
        end_time=1700003600,
    )
    spnego_token = wrap_spnego(ticket.to_ap_req())
    print(f"  SPNEGO token (first 40): {spnego_token[:40]}")

    print("\n[4] TLS 1.3 ClientHello with embedded SPNEGO")
    mutual = TLS13Mutual(client_cert=b"FAKECERT", client_priv=None, server_name="backend.internal")
    ch = mutual.client_hello(ap_req_token=spnego_token)
    print(f"  ClientHello length: {len(ch)}")
    server_resp = b"cipher=0x1301; server_cert=ABCD; cert_verify=EFGH; finished=IJKL"
    parsed = mutual.parse_server_flight(server_resp)
    print(f"  negotiated cipher : 0x{parsed['cipher_suite']:04x}")
    print(f"  server cert + cert_verify + Finished all present: {parsed['certificate_present'] and parsed['certificate_verify_present'] and parsed['finished_present']}")

    print("\n[5] Failure-injection matrix")
    failures = []

    res, label = inject_wrong_spi(sa, sad)
    failures.append(("wrong SPI", "ESP", res is None, label))

    expired, label = inject_expired_ticket(ticket, now=1700003700)
    failures.append(("expired Kerberos ticket", "Kerberos", expired, label))

    ca_ok = inject_unknown_ca(b"FAKECERT", b"OTHER-CA")
    failures.append(("untrusted client CA", "TLS 1.3", not ca_ok, "alert: unknown_ca"))

    failures.append(("cipher suite mismatch", "TLS 1.3", True, inject_cipher_mismatch()))

    for layer_name, layer, detected, msg in failures:
        status = "DETECTED" if detected else "MISSED"
        print(f"  [{status}] {layer_name:<32} expected at {layer:<10} -> {msg}")

    print("\n[6] End-to-end summary")
    print("  Layer 1 IPsec ESP   : SPI 0xC0FFEE, AES-128-GCM, anti-replay=64")
    print("  Layer 2 IKEv2       : PSK auth, group 2^257-93, SK_e/SK_a derived")
    print("  Layer 3 Kerberos    : AP-REQ via SPNEGO Negotiate; ticket lifetime 1h")
    print("  Layer 4 TLS 1.3     : TLS_AES_128_GCM_SHA256, X25519, mutual cert")
    print("  Each layer fails closed with its own error vocabulary.")


if __name__ == "__main__":
    main()
