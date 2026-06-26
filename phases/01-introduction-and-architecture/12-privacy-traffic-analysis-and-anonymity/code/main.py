"""Privacy, Traffic Snooping, and Anonymous Communication.

A stdlib-only demonstration of three core ideas from the lesson:

1. Onion routing -- a Tor-style circuit where a 512-byte cell is wrapped in
   three layers of symmetric encryption (AES-256-CTR-style). Each relay peels
   only its own layer, so no single relay sees both the client and destination.

2. Traffic analysis on a recorded packet trace -- extract the size, timing,
   count, and direction features a website-fingerprinting classifier would
   use, WITHOUT ever decrypting the payload. Encryption hides bytes, not
   metadata.

3. Intersection / traffic-confirmation attack -- given observation windows
   logging which users were online and which circuit to a target was active,
   narrow the suspect set one window at a time. Each window roughly halves
   the set; long observation defeats low-rotation anonymity.

4. Cookie stitching -- the application-layer re-identification hole that
   defeats network-layer anonymity if the user logs in.

Run:  python3 main.py
No third-party packages, no network access.
"""

from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Onion routing: layered stream encryption with a per-relay key.
# ---------------------------------------------------------------------------
# We use a tiny pure-Python CTR-mode stream built on hashlib -- NOT a real
# cipher and NOT secure, but it gives the exact layered-encryption /
# layered-decryption behaviour that illustrates Tor's circuit construction
# without pulling in a cryptography dependency. Do NOT use this for real
# traffic. The point of the lesson is the LAYERING, not the primitive.


def _ctr_keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    """Generate `length` bytes of CTR keystream by hashing key||nonce||ctr.

    Stands in for AES-256-CTR. SHA-256 yields 32-byte blocks; we slice.
    """
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(
            hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
        )
        counter += 1
    return bytes(out[:length])


def onion_encrypt(cell: bytes, keys: List[bytes], nonce: bytes) -> bytes:
    """Wrap `cell` in layers of encryption, inside-out.

    onion = ENC(K_exit, ENC(K_middle, ENC(K_guard, cell)))
    The first key in the list is the INNERMOST (exit) layer; the last is the
    OUTERMOST (guard) layer, which the guard relay strips first.
    """
    payload = cell
    for k in keys:  # exit first, guard last
        ks = _ctr_keystream(k, nonce, len(payload))
        payload = bytes(b ^ ks[i] for i, b in enumerate(payload))
    return payload


def onion_decrypt_layer(payload: bytes, key: bytes, nonce: bytes) -> bytes:
    """Strip ONE layer of the onion using `key` (XOR is symmetric)."""
    ks = _ctr_keystream(key, nonce, len(payload))
    return bytes(b ^ ks[i] for i, b in enumerate(payload))


@dataclass
class Relay:
    name: str
    key: bytes
    predecessor: str
    successor: str

    def sees(self) -> str:
        return (
            f"{self.name} sees predecessor={self.predecessor}, "
            f"successor={self.successor}"
        )


def build_circuit() -> Tuple[bytes, List[Relay], bytes, List[bytes]]:
    """Build a 3-relay Tor-style circuit and a 512-byte cell to send."""
    cell = hashlib.sha256(b"this is a real 512-byte cell payload").digest()
    cell += hashlib.sha256(b"part-two").digest()
    cell += hashlib.sha256(b"part-three").digest()
    cell += hashlib.sha256(b"part-four").digest()  # 128 bytes
    cell += bytes(512 - len(cell))  # pad to a fixed 512-byte Tor-style cell

    k_guard = hashlib.sha256(b"guard-session-key").digest()
    k_middle = hashlib.sha256(b"middle-session-key").digest()
    k_exit = hashlib.sha256(b"exit-session-key").digest()
    nonce = hashlib.sha256(b"circuit-nonce").digest()[:16]

    relays = [
        Relay("guard", k_guard, "Alice(10.0.0.5)", "middle(relay2)"),
        Relay("middle", k_middle, "guard(relay1)", "exit(relay3)"),
        Relay("exit", k_exit, "middle(relay2)", "news.example(203.0.113.44)"),
    ]
    # exit first (innermost), guard last (outermost)
    keys = [k_exit, k_middle, k_guard]
    return cell, relays, nonce, keys


def relay_forward(onion: bytes, relays: List[Relay], nonce: bytes) -> bytes:
    """Each relay peels its layer in turn. Print what each relay learns."""
    payload = onion
    for relay in relays:
        payload = onion_decrypt_layer(payload, relay.key, nonce)
        print(f"    {relay.sees()}  |  after peel: {len(payload)} bytes")
    return payload


# ---------------------------------------------------------------------------
# Traffic analysis: extract metadata features from a packet trace.
# ---------------------------------------------------------------------------


@dataclass
class Packet:
    direction: int  # +1 client->server, -1 server->client
    size: int       # bytes on the wire (incl. headers)
    ts: float       # relative timestamp in seconds


@dataclass
class TraceFeatures:
    total_bytes: int
    packet_count: int
    up_count: int
    down_count: int
    direction_ratio: float
    size_histogram: Dict[int, int]
    interarrival_mean_ms: float
    interarrival_std_ms: float
    burst_count: int

    def report(self) -> str:
        buckets = ", ".join(
            f"{lo}-{lo + 199}={n}" for lo, n in sorted(self.size_histogram.items())
        )
        return "\n".join(
            [
                f"  total bytes      : {self.total_bytes}",
                f"  packet count     : {self.packet_count}  "
                f"(up={self.up_count}, down={self.down_count})",
                f"  direction ratio  : {self.direction_ratio:+.3f}  "
                f"(+1 = mostly uploads)",
                f"  interarrival     : mean={self.interarrival_mean_ms:.1f} ms "
                f"std={self.interarrival_std_ms:.1f} ms",
                f"  bursts (>3 pkts <50ms apart): {self.burst_count}",
                f"  size buckets     : {buckets}",
            ]
        )


def fingerprint_features(trace: List[Packet]) -> TraceFeatures:
    """The features a website-fingerprinting classifier would extract.

    None of this requires decrypting the payload -- it is pure metadata.
    """
    total = sum(p.size for p in trace)
    up = sum(1 for p in trace if p.direction > 0)
    down = len(trace) - up
    ratio = (sum(p.direction for p in trace) / len(trace)) if trace else 0.0

    hist: Dict[int, int] = {}
    for p in trace:
        bucket = (p.size // 200) * 200
        hist[bucket] = hist.get(bucket, 0) + 1

    iats = [
        (trace[i].ts - trace[i - 1].ts) * 1000.0 for i in range(1, len(trace))
    ]
    iat_mean = statistics.fmean(iats) if iats else 0.0
    iat_std = statistics.pstdev(iats) if len(iats) > 1 else 0.0

    bursts = 0
    run = 1
    for i in range(1, len(trace)):
        if (trace[i].ts - trace[i - 1].ts) * 1000.0 < 50.0:
            run += 1
        else:
            if run > 3:
                bursts += 1
            run = 1
    if run > 3:
        bursts += 1

    return TraceFeatures(
        total_bytes=total,
        packet_count=len(trace),
        up_count=up,
        down_count=down,
        direction_ratio=ratio,
        size_histogram=hist,
        interarrival_mean_ms=iat_mean,
        interarrival_std_ms=iat_std,
        burst_count=bursts,
    )


def sample_trace() -> List[Packet]:
    """A synthetic TLS trace: a GET, then a large image burst, then close.

    Mimics a page load of news.example: a small request, a 1500-byte response,
    a gap, then a burst of 1400-byte image segments.
    """
    return [
        Packet(+1, 600, 0.000),
        Packet(-1, 1500, 0.120),
        Packet(-1, 1400, 1.310),
        Packet(-1, 1400, 1.312),
        Packet(-1, 1400, 1.314),
        Packet(-1, 1400, 1.316),
        Packet(-1, 1400, 1.318),
        Packet(+1, 80, 1.340),
        Packet(-1, 1400, 1.360),
        Packet(-1, 1400, 1.362),
        Packet(-1, 900, 1.364),
        Packet(+1, 80, 1.500),
    ]


# ---------------------------------------------------------------------------
# Intersection attack: narrow the suspect set across observation windows.
# ---------------------------------------------------------------------------


@dataclass
class Window:
    """One observation window: who was online, was the target circuit up."""
    online: List[str]
    target_active: bool


def intersection_attack(
    suspects: List[str], windows: List[Window]
) -> List[List[str]]:
    """Return the surviving suspect set after each window.

    Rule: if the circuit to the target was active in a window, only users who
    were online in that window could have been the source. Intersect.
    """
    remaining = list(suspects)
    history: List[List[str]] = []
    for w in windows:
        if w.target_active:
            online = set(w.online)
            remaining = [u for u in remaining if u in online]
        history.append(list(remaining))
    return history


# ---------------------------------------------------------------------------
# Cookie flow analyzer: the application-layer re-identification hole.
# ---------------------------------------------------------------------------


@dataclass
class Session:
    session_id: str
    dest_ip: str
    sni: str
    cookie_id: str | None


def stitch_by_cookie(sessions: List[Session]) -> Dict[str, List[str]]:
    """Group sessions that share a cookie id -- the privacy layer Tor can't fix."""
    groups: Dict[str, List[str]] = {}
    for s in sessions:
        if s.cookie_id is None:
            continue
        groups.setdefault(s.cookie_id, []).append(s.session_id)
    return {k: v for k, v in groups.items() if len(v) > 1}


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 72)
    print("1. ONION ROUTING -- three-layer Tor-style circuit")
    print("=" * 72)
    cell, relays, nonce, keys = build_circuit()
    print("  Alice builds a 512-byte cell and a 3-relay circuit.")
    print(f"  relays: {[r.name for r in relays]}")
    onion = onion_encrypt(cell, keys, nonce)
    print(f"  onion (outermost): {len(onion)} bytes, first 8 = {onion[:8].hex()}")
    print("  forwarding through relays (each peels its layer):")
    recovered = relay_forward(onion, relays, nonce)
    print("  exit hands destination: news.example(203.0.113.44)")
    print(f"  round-trip OK? {recovered == cell}")

    print()
    print("=" * 72)
    print("2. TRAFFIC ANALYSIS -- features from a captured TLS trace")
    print("=" * 72)
    trace = sample_trace()
    feats = fingerprint_features(trace)
    print("  (no decryption performed -- pure metadata)")
    print(feats.report())
    print("  -> an adversary can fingerprint the site from these alone.")

    print()
    print("=" * 72)
    print("3. INTERSECTION ATTACK -- narrow the suspect set")
    print("=" * 72)
    suspects = [f"User{i}" for i in range(16)]
    windows = [
        Window(["User0", "User1", "User2", "User3"], True),
        Window(["User1", "User4", "User5", "User9"], True),
        Window(["User1", "User2", "User6", "User7"], True),
        Window(["User1", "User8", "User10", "User11"], True),
        Window(["User1", "User12", "User13", "User14"], True),
    ]
    history = intersection_attack(suspects, windows)
    for i, (w, surv) in enumerate(zip(windows, history)):
        print(f"  window {i}: online={w.online} -> {len(surv)} suspects: {surv}")
    print(f"  => after {len(windows)} windows the adversary isolated: {history[-1]}")
    print("  (this is why Tor rotates circuits every ~10 minutes.)")

    print()
    print("=" * 72)
    print("4. COOKIE STITCHING -- the application-layer anonymity hole")
    print("=" * 72)
    sessions = [
        Session("sess-A", "203.0.113.44", "news.example", "id=abc123"),
        Session("sess-B", "203.0.113.44", "news.example", None),
        Session("sess-C", "203.0.113.9", "mail.example", "id=abc123"),
        Session("sess-D", "203.0.113.44", "news.example", "id=xyz789"),
        Session("sess-E", "203.0.113.9", "mail.example", "id=xyz789"),
    ]
    groups = stitch_by_cookie(sessions)
    for cookie, sids in groups.items():
        print(f"  cookie {cookie} stitches: {sids}")
    print("  -> logging in over Tor re-identifies you at the application layer.")

    print()
    print("=" * 72)
    print("Done. Key takeaway: encryption hides content, NOT metadata.")
    print("=" * 72)


if __name__ == "__main__":
    main()
