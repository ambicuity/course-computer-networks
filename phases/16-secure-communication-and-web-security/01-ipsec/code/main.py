"""IPsec Security Association (SA) simulator.

Models an IPsec SA with negotiated parameters (SPI, algorithms, mode)
and simulates packet processing through transport and tunnel modes.
Demonstrates anti-replay via sequence numbers and AH/ESP header layouts.
stdlib-only, educational — no real crypto.
"""

from __future__ import annotations
import hashlib
import hmac
import struct
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IPsecSA:
    """A simplex Security Association between two endpoints."""
    spi: int
    dest_ip: str
    protocol: str          # "AH" or "ESP"
    mode: str              # "transport" or "tunnel"
    enc_alg: str           # e.g. "AES-128-CBC" or "NULL"
    auth_alg: str          # e.g. "HMAC-SHA1"
    shared_key: bytes
    src_gateway: Optional[str] = None   # for tunnel mode
    dst_gateway: Optional[str] = None  # for tunnel mode
    seq: int = 0
    replay_window: set = field(default_factory=set)
    max_seq: int = 0xFFFFFFFF
    bytes_in: int = 0
    bytes_out: int = 0

    def next_seq(self) -> int:
        if self.seq >= self.max_seq:
            raise RuntimeError(
                f"SA 0x{self.spi:08X}: sequence space exhausted, new SA required"
            )
        self.seq += 1
        return self.seq

    def check_replay(self, seq_num: int) -> bool:
        if seq_num in self.replay_window:
            return False  # replay detected
        self.replay_window.add(seq_num)
        return True

    def compute_hmac(self, data: bytes) -> bytes:
        return hmac.new(self.shared_key, data, hashlib.sha1).digest()[:12]


def build_ah_header(sa: IPsecSA, next_header: int) -> bytes:
    """Build a 12-byte AH header (fixed part) + HMAC placeholder."""
    payload_len = 4  # 6 32-bit words minus 2
    reserved = 0
    seq = sa.next_seq()
    header = struct.pack("!BBII", next_header, payload_len, reserved, sa.spi)
    header += struct.pack("!I", seq)
    return header, seq


def build_esp_header(sa: IPsecSA) -> tuple[bytes, int]:
    """Build an 8-byte ESP header (SPI + Seq) + IV placeholder."""
    seq = sa.next_seq()
    header = struct.pack("!II", sa.spi, seq)
    iv = b"\x00" * 16  # placeholder IV (AES block size)
    return header + iv, seq


def simulate_transport_mode(sa: IPsecSA, ip_header: bytes,
                             tcp_header: bytes, payload: bytes) -> dict:
    """Simulate IPsec transport-mode encapsulation."""
    if sa.protocol == "AH":
        ah_hdr, seq = build_ah_header(sa, next_header=6)
        hmac_data = ip_header + ah_hdr + tcp_header + payload
        auth = sa.compute_hmac(hmac_data)
        total = len(ip_header) + len(ah_hdr) + len(auth) + len(tcp_header) + len(payload)
        sa.bytes_out += total
        return {
            "mode": "transport", "protocol": "AH", "seq": seq,
            "overhead_bytes": len(ah_hdr) + len(auth),
            "total_bytes": total, "authenticated": "ip_header+ah+tcp+payload",
            "encrypted": "none",
        }
    else:  # ESP
        esp_hdr, seq = build_esp_header(sa)
        enc_payload = payload  # not actually encrypted in sim
        hmac_data = esp_hdr + tcp_header + enc_payload
        auth = sa.compute_hmac(hmac_data)
        total = len(ip_header) + len(esp_hdr) + len(tcp_header) + len(enc_payload) + len(auth)
        sa.bytes_out += total
        return {
            "mode": "transport", "protocol": "ESP", "seq": seq,
            "overhead_bytes": len(esp_hdr) + len(auth),
            "total_bytes": total, "authenticated": "esp_hdr+tcp+payload (HMAC trailer)",
            "encrypted": "tcp_header+payload",
        }


def simulate_tunnel_mode(sa: IPsecSA, old_ip: bytes, tcp: bytes,
                         payload: bytes) -> dict:
    """Simulate IPsec tunnel-mode encapsulation with a new IP header."""
    new_ip = struct.pack("!4s4s", _ip_bytes(sa.src_gateway), _ip_bytes(sa.dst_gateway))
    new_ip = b"\x45\x00" + b"\x00\x00" * 9 + new_ip  # simplified 20-byte header
    if sa.protocol == "ESP":
        esp_hdr, seq = build_esp_header(sa)
        enc = old_ip + tcp + payload
        auth = sa.compute_hmac(esp_hdr + enc)
        total = len(new_ip) + len(esp_hdr) + len(enc) + len(auth)
        sa.bytes_out += total
        return {
            "mode": "tunnel", "protocol": "ESP", "seq": seq,
            "overhead_bytes": len(new_ip) + len(esp_hdr) + len(auth),
            "total_bytes": total, "outer_src": sa.src_gateway,
            "outer_dst": sa.dst_gateway, "encrypted": "old_ip+tcp+payload",
            "authenticated": "esp_hdr+enc (HMAC trailer)",
        }
    ah_hdr, seq = build_ah_header(sa, next_header=4)
    auth = sa.compute_hmac(new_ip + ah_hdr + old_ip + tcp + payload)
    total = len(new_ip) + len(ah_hdr) + len(auth) + len(old_ip) + len(tcp) + len(payload)
    sa.bytes_out += total
    return {
        "mode": "tunnel", "protocol": "AH", "seq": seq,
        "overhead_bytes": len(new_ip) + len(ah_hdr) + len(auth),
        "total_bytes": total, "outer_src": sa.src_gateway,
        "outer_dst": sa.dst_gateway,
    }


def _ip_bytes(addr: str) -> bytes:
    return bytes(int(o) for o in addr.split("."))


def negotiate_sa(spi: int, proto: str, mode: str, enc: str,
                 auth: str, key: bytes, src_gw: str = "", dst_gw: str = "") -> IPsecSA:
    """Simulate IKEv2 SA negotiation."""
    print(f"[IKEv2] Negotiating SA: SPI=0x{spi:08X} proto={proto} mode={mode}")
    print(f"[IKEv2]   enc={enc}  auth={auth}  key_len={len(key)} bytes")
    if proto not in ("AH", "ESP"):
        raise ValueError(f"Unsupported protocol: {proto}")
    if mode not in ("transport", "tunnel"):
        raise ValueError(f"Unsupported mode: {mode}")
    sa = IPsecSA(
        spi=spi, dest_ip=dst_gw or "10.0.0.2", protocol=proto, mode=mode,
        enc_alg=enc, auth_alg=auth, shared_key=key,
        src_gateway=src_gw or None, dst_gateway=dst_gw or None,
    )
    print(f"[IKEv2] SA established: ({spi:#010X}, {sa.dest_ip}, {proto})")
    return sa


def main() -> None:
    print("=" * 72)
    print("IPsec SA Simulator — transport and tunnel mode")
    print("=" * 72)

    key = b"shared-secret-key-for-demo-only!"

    # --- Transport mode ESP ---
    sa_t = negotiate_sa(0x0000A1B2, "ESP", "transport", "AES-128-CBC",
                         "HMAC-SHA1", key)
    ip_hdr = b"\x45\x00" + b"\x00" * 18   # 20-byte IPv4 header placeholder
    tcp_hdr = b"\x00" * 20               # 20-byte TCP header placeholder
    payload = b"GET /index.html HTTP/1.1\r\n\r\n"
    r1 = simulate_transport_mode(sa_t, ip_hdr, tcp_hdr, payload)
    print(f"\n[Transport ESP] seq={r1['seq']} overhead={r1['overhead_bytes']}B "
          f"total={r1['total_bytes']}B")
    print(f"  encrypted: {r1['encrypted']}")
    print(f"  authenticated: {r1['authenticated']}")

    # --- Tunnel mode ESP (VPN) ---
    sa_v = negotiate_sa(0xC0FFEE01, "ESP", "tunnel", "AES-128-CBC",
                         "HMAC-SHA1", key, "192.168.1.1", "192.168.2.1")
    r2 = simulate_tunnel_mode(sa_v, ip_hdr, tcp_hdr, payload)
    print(f"\n[Tunnel ESP] seq={r2['seq']} overhead={r2['overhead_bytes']}B "
          f"total={r2['total_bytes']}B")
    print(f"  outer: {r2['outer_src']} -> {r2['outer_dst']}")
    print(f"  encrypted: {r2['encrypted']}")

    # --- AH transport mode ---
    sa_a = negotiate_sa(0x0000C3D4, "AH", "transport", "NULL",
                         "HMAC-SHA1", key)
    r3 = simulate_transport_mode(sa_a, ip_hdr, tcp_hdr, payload)
    print(f"\n[Transport AH] seq={r3['seq']} overhead={r3['overhead_bytes']}B "
          f"total={r3['total_bytes']}B")
    print(f"  authenticated: {r3['authenticated']} (no encryption)")

    # --- Anti-replay test ---
    print("\n" + "=" * 72)
    print("Anti-replay test")
    print("=" * 72)
    test_sa = negotiate_sa(0xDEADBEEF, "ESP", "transport", "AES-128-CBC",
                            "HMAC-SHA1", key)
    for s in [1, 2, 3]:
        ok = test_sa.check_replay(s)
        print(f"  seq={s} -> {'accepted' if ok else 'REPLAY!'}")
    dup = test_sa.check_replay(2)
    print(f"  seq=2 (repeat) -> {'accepted' if dup else 'REPLAY DETECTED'}")

    # --- Sequence exhaustion ---
    print("\n[Sequence exhaustion] max_seq = 0x{:08X}".format(test_sa.max_seq))
    print("  (In production: after 2^32 packets, a new SA must be established.)")

    # --- AH header layout ---
    print("\n" + "=" * 72)
    print("AH header layout (12 bytes fixed + variable HMAC):")
    print("  Next Header | Payload Len | Reserved | SPI | Seq | Auth Data")
    print("ESP header layout (8 bytes + 16-byte IV):")
    print("  SPI | Sequence Number | IV(16) | ... encrypted payload ... | HMAC")
    print("=" * 72)


if __name__ == "__main__":
    main()
