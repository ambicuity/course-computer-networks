from __future__ import annotations

"""Copyright lesson demonstration.

Simulates concepts covered in the "Copyright" lesson of a computer networks
course: content fingerprinting, DRM key management, the contrast between
centralised file-sharing indexes (Napster) and decentralised hash tables
(BitTorrent DHT), copyright duration, and common online enforcement
mechanisms.

Only the Python standard library is used.
"""

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator


# ---------------------------------------------------------------------------
# 1. Content fingerprinting (perceptual hash comparison)
# ---------------------------------------------------------------------------

def _simple_chunk_hash(data: bytes, chunk_size: int = 64) -> list[str]:
    """Return a list of hex chunk hashes for *data*.

    This is a didactic stand-in for a perceptual hashing algorithm such as
    pHash.  It divides the byte stream into fixed-size chunks and hashes each
    chunk with SHA-256.
    """
    hashes: list[str] = []
    for offset in range(0, len(data), chunk_size):
        chunk = data[offset : offset + chunk_size]
        hashes.append(hashlib.sha256(chunk).hexdigest())
    return hashes


def compare_fingerprints(original: bytes, suspect: bytes) -> dict[str, float]:
    """Compare two byte sequences using a simple perceptual fingerprint.

    Returns a dict with the chunk match ratio, the Hamming-style bit
    difference between the overall hashes, and a boolean *likely_match* flag
    that is True when enough chunk hashes agree.
    """
    original_chunks = _simple_chunk_hash(original)
    suspect_chunks = _simple_chunk_hash(suspect)

    matches = sum(
        1
        for orig, susp in zip(original_chunks, suspect_chunks)
        if orig == susp
    )
    max_chunks = max(len(original_chunks), len(suspect_chunks), 1)
    chunk_ratio = matches / max_chunks

    full_original = hashlib.sha256(original).digest()
    full_suspect = hashlib.sha256(suspect).digest()
    bit_difference = (
        sum(
            (ob ^ sb).bit_count()
            for ob, sb in zip(full_original, full_suspect)
        )
        / 256.0
    )

    likely_match = chunk_ratio >= 0.85 and bit_difference <= 0.10
    return {
        "chunk_match_ratio": chunk_ratio,
        "overall_bit_difference": bit_difference,
        "likely_match": likely_match,
    }


# ---------------------------------------------------------------------------
# 2. DRM key management
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DrmLicense:
    """A minimal immutable license record."""

    content_id: str
    rights: str
    expiry_epoch: int
    signature: bytes

    def is_valid(self, master_key: bytes) -> bool:
        """Verify that the license signature matches its contents."""
        payload = self._payload()
        expected = hmac.new(master_key, payload, hashlib.sha256).digest()
        return hmac.compare_digest(expected, self.signature)

    def _payload(self) -> bytes:
        parts = f"{self.content_id}|{self.rights}|{self.expiry_epoch}"
        return parts.encode("utf-8")

    def to_b64(self) -> str:
        """Serialise the license to a base64 string."""
        raw = (
            self.content_id.encode("utf-8")
            + b"\x00"
            + self.rights.encode("utf-8")
            + b"\x00"
            + str(self.expiry_epoch).encode("utf-8")
            + b"\x00"
            + self.signature
        )
        return base64.b64encode(raw).decode("ascii")

    @classmethod
    def from_b64(cls, encoded: str) -> DrmLicense:
        """Parse a base64 serialised license."""
        raw = base64.b64decode(encoded)
        content_id, rights, expiry_str, signature = raw.split(b"\x00", 3)
        return cls(
            content_id=content_id.decode("utf-8"),
            rights=rights.decode("utf-8"),
            expiry_epoch=int(expiry_str.decode("utf-8")),
            signature=signature,
        )


def _derive_key(master_key: bytes, content_id: str) -> bytes:
    """Derive a content-specific encryption key from the master key."""
    return hmac.new(master_key, content_id.encode("utf-8"), hashlib.sha256).digest()


def encrypt_content(master_key: bytes, content_id: str, plaintext: bytes) -> bytes:
    """Encrypt plaintext with a key derived from *master_key* and *content_id*.

    Uses a simple XOR stream cipher with a SHA-256 based keystream.  This is
    intentionally lightweight and unsuitable for real DRM systems; it exists only
    to illustrate the separation between a content key and a license.
    """
    key = _derive_key(master_key, content_id)
    ciphertext = bytearray()
    for i, byte in enumerate(plaintext):
        keystream_byte = key[i % len(key)]
        ciphertext.append(byte ^ keystream_byte)
    return bytes(ciphertext)


def decrypt_content(
    master_key: bytes, content_id: str, ciphertext: bytes
) -> bytes:
    """Decrypt ciphertext that was encrypted with *encrypt_content*.

    XOR encryption and decryption are symmetric, so this function reuses the
    same keystream generation.
    """
    return encrypt_content(master_key, content_id, ciphertext)


def issue_license(
    master_key: bytes, content_id: str, rights: str, expiry_epoch: int
) -> DrmLicense:
    """Create and sign a *DrmLicense* for the given content."""
    payload = f"{content_id}|{rights}|{expiry_epoch}".encode("utf-8")
    signature = hmac.new(master_key, payload, hashlib.sha256).digest()
    return DrmLicense(content_id, rights, expiry_epoch, signature)


def verify_license_and_decrypt(
    master_key: bytes,
    license_b64: str,
    ciphertext: bytes,
    content_id: str,
    now_epoch: int | None = None,
) -> bytes:
    """Verify *license_b64*, check expiry, then decrypt *ciphertext*.

    Raises ValueError if the license is invalid or expired.
    """
    license = DrmLicense.from_b64(license_b64)
    if license.content_id != content_id:
        raise ValueError(f"License content mismatch: {license.content_id!r}")
    if not license.is_valid(master_key):
        raise ValueError("License signature is invalid")
    if now_epoch is None:
        now_epoch = int(datetime.now().timestamp())
    if now_epoch > license.expiry_epoch:
        raise ValueError("License has expired")
    return decrypt_content(master_key, content_id, ciphertext)


# ---------------------------------------------------------------------------
# 3. Napster centralised index vs BitTorrent DHT
# ---------------------------------------------------------------------------

@dataclass
class NapsterIndex:
    """A centralised filename-to-host mapping (Napster-style)."""

    host: str = "napster.central.server"
    _index: dict[str, list[str]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self._index is None:
            self._index = {}

    def publish(self, filename: str, peer: str) -> None:
        """Register *peer* as a host for *filename*."""
        self._index.setdefault(filename, []).append(peer)

    def lookup(self, filename: str) -> list[str]:
        """Return the list of peers hosting *filename*."""
        return list(self._index.get(filename, []))


@dataclass
class BittorrentDht:
    """A simplified Distributed Hash Table (BitTorrent-style)."""

    node_id: str
    _routing_table: dict[str, list[str]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self._routing_table is None:
            self._routing_table = {}

    def _distance(self, a: str, b: str) -> int:
        """XOR metric between two 160-bit hex node identifiers."""
        return int(a, 16) ^ int(b, 16)

    def store(self, info_hash: str, peer: str) -> None:
        """Store a peer contact for *info_hash*."""
        self._routing_table.setdefault(info_hash, []).append(peer)

    def find_peers(self, info_hash: str) -> list[str]:
        """Return the peers closest to *info_hash* in the DHT."""
        if info_hash in self._routing_table:
            return list(self._routing_table[info_hash])
        # No exact match: return peers whose stored hashes are closest.
        sorted_hashes = sorted(
            self._routing_table,
            key=lambda key: self._distance(key, info_hash),
        )
        peers: list[str] = []
        for key in sorted_hashes[:3]:
            peers.extend(self._routing_table[key])
        return peers


def napster_vs_bittorrent() -> dict[str, dict[str, str]]:
    """Return a comparison table of Napster and BitTorrent architectures."""
    return {
        "Napster": {
            "architecture": "centralised index",
            "lookup": "query central server by filename",
            "single_point_of_failure": "yes",
            "legal_vulnerability": "central server can be shut down",
        },
        "BitTorrent": {
            "architecture": "decentralised DHT / tracker swarm",
            "lookup": "query peers by info hash",
            "single_point_of_failure": "no",
            "legal_vulnerability": "no central index to seize",
        },
    }


# ---------------------------------------------------------------------------
# 4. Copyright duration
# ---------------------------------------------------------------------------

def copyright_duration(creation_year: int, current_year: int | None = None) -> dict[str, int]:
    """Calculate copyright duration for a U.S. work created in *creation_year*.

    Uses the current rule for individual authors: life of the author plus
    70 years.  Because we cannot know the author's death year, we report
    elapsed years and the remaining years assuming publication in the
    creation year and death 30 years later.
    """
    if current_year is None:
        current_year = datetime.now().year
    if creation_year > current_year:
        raise ValueError("creation_year cannot be in the future")

    assumed_death_year = creation_year + 30
    expiration_year = assumed_death_year + 70
    years_elapsed = current_year - creation_year
    years_remaining = max(0, expiration_year - current_year)
    return {
        "creation_year": creation_year,
        "assumed_death_year": assumed_death_year,
        "expiration_year": expiration_year,
        "years_elapsed": years_elapsed,
        "years_remaining": years_remaining,
    }


# ---------------------------------------------------------------------------
# 5. Enforcement mechanisms table
# ---------------------------------------------------------------------------

def enforcement_mechanisms_table() -> str:
    """Return an ASCII table of common copyright enforcement mechanisms."""
    rows = [
        ("Mechanism", "What it does", "Example"),
        ("Watermarking", "Embeds visible/hidden owner info", "Stock photo logo"),
        ("Fingerprinting", "Matches content against database", "YouTube Content ID"),
        ("DRM", "Encrypts content and checks license", "Streaming movie keys"),
        ("Legal", "Takedown notices, lawsuits", "DMCA 512 notice"),
    ]
    col_widths = [
        max(len(row[i]) for row in rows) for i in range(len(rows[0]))
    ]
    lines: list[str] = []
    for idx, row in enumerate(rows):
        line = " | ".join(
            cell.ljust(col_widths[i]) for i, cell in enumerate(row)
        )
        lines.append(line)
        if idx == 0:
            lines.append("-" * len(line))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------

def _demo() -> None:
    """Run small examples of each module capability."""
    print("=== 1. Fingerprinting ===")
    original = b"The quick brown fox jumps over the lazy dog."
    suspect = original.replace(b"quick", b"fast")
    print(compare_fingerprints(original, suspect))

    print("\n=== 2. DRM ===")
    master = secrets.token_bytes(32)
    content_id = "lesson-16-09-copyright"
    plaintext = b"Copyrighted course video segment"
    ciphertext = encrypt_content(master, content_id, plaintext)
    license = issue_license(
        master, content_id, "view-only", int(datetime.now().timestamp()) + 3600
    )
    decrypted = verify_license_and_decrypt(master, license.to_b64(), ciphertext, content_id)
    print("Decrypted matches original:", decrypted == plaintext)

    print("\n=== 3. Napster vs BitTorrent ===")
    napster = NapsterIndex()
    napster.publish("song.mp3", "peer-1")
    print("Napster peers for song.mp3:", napster.lookup("song.mp3"))

    dht = BittorrentDht("abc123")
    info_hash = "deadbeef" * 5
    dht.store(info_hash, "peer-a")
    print("DHT peers:", dht.find_peers(info_hash))
    for key, value in napster_vs_bittorrent().items():
        print(key, value)

    print("\n=== 4. Copyright duration ===")
    print(copyright_duration(2010))

    print("\n=== 5. Enforcement mechanisms ===")
    print(enforcement_mechanisms_table())


if __name__ == "__main__":
    _demo()
