"""Secure Naming to SSL — DNS spoofing, DNSsec verification, and the SSL/TLS
handshake, modeled with stdlib only.

Demonstrates three things an engineer must be able to reason about before
relying on HTTPS:
  1. DNS cache poisoning: Trudy races a forged reply (matching 16-bit query ID
     + source port) against the real one; the forged RRSet wins if it lands first.
  2. DNSsec: each RRSet is signed with the zone private key; a forged RRSet fails
     signature verification with the zone public key, so the cache rejects it.
  3. The SSL 3 / TLS handshake: client_hello -> server_hello + certificate ->
     key exchange (premaster encrypted with server public key) -> finished MAC.
     Both sides derive the same session keys from premaster + nonces via a PRF.

No pip deps. Uses RSA-style modular exponentiation and HMAC-SHA256 for the PRF.

Run:  python3 main.py    Exit: 0.
"""
from __future__ import annotations

import hashlib
import hmac
import random
from dataclasses import dataclass, field

random.seed(11)


# --------------------------------------------------------------------------- #
# Tiny RSA (textbook, small primes) for the SSL key-exchange demo             #
# --------------------------------------------------------------------------- #
def is_prime(n: int) -> bool:
    if n < 2:
        return False
    for f in (2, 3, 5, 7, 11, 13):
        if n % f == 0:
            return n == f
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if a >= n:
            continue
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def gen_keypair(bits: int = 64) -> tuple[tuple[int, int], tuple[int, int]]:
    """Return ((pub_e, n), (priv_d, n)) with small primes for demo speed."""
    def rand_prime() -> int:
        while True:
            p = random.getrandbits(bits) | 1 | (1 << (bits - 1))
            if is_prime(p):
                return p
    p, q = rand_prime(), rand_prime()
    n = p * q
    phi = (p - 1) * (q - 1)
    e = 65537
    d = pow(e, -1, phi)
    return (e, n), (d, n)


def rsa_enc(pub: tuple[int, int], m: int) -> int:
    e, n = pub
    assert 0 <= m < n
    return pow(m, e, n)


def rsa_dec(priv: tuple[int, int], c: int) -> int:
    d, n = priv
    return pow(c, d, n)


# --------------------------------------------------------------------------- #
# DNS spoofing                                                                 #
# --------------------------------------------------------------------------- #
@dataclass
class DNSQuery:
    qname: str
    query_id: int          # 16-bit
    src_port: int          # 16-bit


@dataclass
class DNSReply:
    qname: str
    query_id: int
    addr: str
    signer: str            # "legit" | "trudy"
    signature: bytes = b""  # DNSsec SIG; empty = unsigned


def dns_poisoning_race(query: DNSQuery, legit_addr: str, trudy_addr: str) -> str:
    """Trudy tries to race a forged reply matching query_id+src_port."""
    # Trudy must guess the 16-bit query id AND the 16-bit source port.
    guess_id = random.randint(0, 0xFFFF)
    guess_port = random.randint(0, 0xFFFF)
    id_ok = guess_id == query.query_id
    port_ok = guess_port == query.src_port
    # Whoever "arrives" first wins the cache slot. Forge lands first only if it
    # matches both fields (otherwise the resolver drops it as garbage).
    forge_wins = id_ok and port_ok and random.random() < 0.5
    return trudy_addr if forge_wins else legit_addr


# --------------------------------------------------------------------------- #
# DNSsec                                                                       #
# --------------------------------------------------------------------------- #
def sign_rrset(priv: tuple[int, int], rrset: bytes) -> bytes:
    """Sign a hashed RRSet with the zone private key (RSA-style, hash mod n)."""
    _, n = priv
    h = int.from_bytes(hashlib.sha256(rrset).digest(), "big") % n
    sig = rsa_dec(priv, h)
    return sig.to_bytes((sig.bit_length() + 7) // 8, "big")


def verify_rrset(pub: tuple[int, int], rrset: bytes, sig: bytes) -> bool:
    _, n = pub
    h = int.from_bytes(hashlib.sha256(rrset).digest(), "big") % n
    s = int.from_bytes(sig, "big")
    recovered = rsa_enc(pub, s)
    return recovered == h


# --------------------------------------------------------------------------- #
# SSL/TLS handshake                                                            #
# --------------------------------------------------------------------------- #
def prf(secret: bytes, label: bytes, seed: bytes, n: int) -> bytes:
    """TLS 1.0 PRF (HMAC-SHA256-based P_hash)."""
    out = b""
    a = hmac.new(secret, label + seed, hashlib.sha256).digest()
    while len(out) < n:
        out += hmac.new(secret, a + label + seed, hashlib.sha256).digest()
        a = hmac.new(secret, a, hashlib.sha256).digest()
    return out[:n]


@dataclass
class ClientHello:
    client_nonce: bytes
    cipher_suites: list[str]


@dataclass
class ServerHello:
    server_nonce: bytes
    chosen_cipher: str
    certificate_pub: tuple[int, int]


@dataclass
class SSLSession:
    premaster: bytes
    client_nonce: bytes
    server_nonce: bytes
    cipher: str

    def master_secret(self) -> bytes:
        return prf(self.premaster, b"master secret",
                   self.client_nonce + self.server_nonce, 48)

    def key_block(self) -> bytes:
        return prf(self.master_secret(), b"key expansion",
                   self.server_nonce + self.client_nonce, 128)

    def client_write_mac_key(self) -> bytes:
        return self.key_block()[:20]

    def server_write_mac_key(self) -> bytes:
        return self.key_block()[20:40]


def ssl_handshake(server_pub: tuple[int, int]) -> tuple[SSLSession, SSLSession]:
    """Both sides end with the same session keys (deterministic given inputs)."""
    client_nonce = random.randbytes(32)
    server_nonce = random.randbytes(32)
    hello = ClientHello(client_nonce, ["TLS_RSA_WITH_AES_128_CBC_SHA", "TLS_RSA_WITH_AES_256_GCM_SHA384"])
    shello = ServerHello(server_nonce, "TLS_RSA_WITH_AES_128_CBC_SHA", server_pub)
    # client generates 48-byte premaster and encrypts with server public key
    premaster = random.randbytes(48)
    _, n = server_pub
    premaster_int = int.from_bytes(premaster, "big") % n
    encrypted = rsa_enc(server_pub, premaster_int)
    # server decrypts with its private key (only the server can do this)
    client_premaster = premaster_int.to_bytes(48, "big")
    client_session = SSLSession(client_premaster, client_nonce, server_nonce, shello.chosen_cipher)
    dec_int = rsa_dec(_server_priv_for_handshake, encrypted)
    # client reduced mod n; recover the 48-byte premaster by zero-padding
    server_premaster = dec_int.to_bytes(48, "big")
    server_session = SSLSession(server_premaster, client_nonce, server_nonce, shello.chosen_cipher)
    return client_session, server_session


# set by main() before calling ssl_handshake(); real life: only server knows this
_server_priv_for_handshake = (0, 0)


def ssl_record_protect(mac_key: bytes, plaintext: bytes) -> tuple[bytes, bytes]:
    """SSL record: MAC-then-encrypt (we show the MAC step; encryption sketched)."""
    mac = hmac.new(mac_key, b"\x17\x03\x03" + len(plaintext).to_bytes(2, "big") + plaintext, hashlib.sha256).digest()
    # (encryption would use the symmetric key from the key block; we XOR-skip it)
    return plaintext, mac


# --------------------------------------------------------------------------- #
# Demonstration                                                                #
# --------------------------------------------------------------------------- #
def main() -> None:
    global _server_priv_for_handshake
    print("=" * 66)
    print("SECURE NAMING TO SSL  --  DNSsec verification + SSL/TLS handshake")
    print("=" * 66)

    # --- DNS spoofing ---
    print("\n[1] DNS cache poisoning (unsigned DNS)")
    query = DNSQuery("bob.com", query_id=0x1234, src_port=0x5566)
    print(f"  query: {query.qname} id={query.query_id:#06x} port={query.src_port:#06x}")
    wins = [dns_poisoning_race(query, "36.1.2.3", "42.9.9.9") for _ in range(20)]
    poisoned = wins.count("42.9.9.9")
    print(f"  over 20 races: poisoned {poisoned} times, legit {20 - poisoned} times")
    print("  (Trudy must match 16-bit id AND 16-bit port; random source ports make this hard)")

    # --- DNSsec ---
    print("\n[2] DNSsec: signed RRSet rejects forged reply")
    zone_pub, zone_priv = gen_keypair(bits=128)
    legit_rrset = b"bob.com A 36.1.2.3 ttl=300"
    legit_sig = sign_rrset(zone_priv, legit_rrset)
    forged_rrset = b"bob.com A 42.9.9.9 ttl=300"
    forged_sig = sign_rrset(zone_priv, forged_rrset)  # Trudy does NOT have zone key
    fake_sig = (12345).to_bytes(8, "big")             # Trudy's garbage signature
    print(f"  legit RRSet verifies: {verify_rrset(zone_pub, legit_rrset, legit_sig)}")
    print(f"  forged RRSet with Trudy's fake sig: {verify_rrset(zone_pub, forged_rrset, fake_sig)}")
    print(f"  forged RRSet re-signed by real key (impossible offline): "
          f"{verify_rrset(zone_pub, forged_rrset, forged_sig)}  (only the zone can do this)")

    # --- SSL handshake ---
    print("\n[3] SSL/TLS handshake: both sides derive identical keys")
    server_pub, server_priv = gen_keypair(bits=512)
    _server_priv_for_handshake = server_priv
    c_sess, s_sess = ssl_handshake(server_pub)
    cm = c_sess.master_secret().hex()
    sm = s_sess.master_secret().hex()
    print(f"  client master_secret: {cm[:32]}...")
    print(f"  server master_secret: {sm[:32]}...")
    print(f"  master secrets match: {cm == sm}")
    print(f"  client_write_mac_key: {c_sess.client_write_mac_key().hex()[:20]}...")
    print(f"  server_write_mac_key: {s_sess.server_write_mac_key().hex()[:20]}...")

    # --- SSL record ---
    print("\n[4] SSL record: MAC-then-encrypt (MAC step shown)")
    pt = b"GET / HTTP/1.1\r\nHost: bob.com\r\n\r\n"
    ct, mac = ssl_record_protect(c_sess.client_write_mac_key(), pt)
    print(f"  plaintext  : {pt!r}")
    print(f"  MAC (HMAC) : {mac.hex()[:32]}...")
    # tamper one byte -> receiver MAC check fails
    tampered = b"GET / HTTP/1.1\r\nHost: eve.com\r\n\r\n"
    _, mac2 = ssl_record_protect(c_sess.client_write_mac_key(), tampered)
    print(f"  tampered MAC differs: {mac != mac2}  -> receiver rejects (integrity)")

    print("\nKey: DNSsec secures naming (SIG over RRSet); SSL/TLS secures the")
    print("channel (cert chain + premaster + nonces -> session keys). HTTPS = HTTP over TLS:443.")
    print("Exit 0.")


if __name__ == "__main__":
    main()
