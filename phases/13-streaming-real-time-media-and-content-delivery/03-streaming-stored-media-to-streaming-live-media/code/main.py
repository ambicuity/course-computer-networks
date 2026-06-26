"""Streaming Stored and Live Media: metafile handoff, FEC, interleaving,
playout buffer.

A stdlib-only demonstration of the core mechanisms of media streaming:
the download-delay problem that motivates metafile streaming, FEC parity
across packets (XOR reconstruction of a single erasure), interleaving
that turns a lost packet into reduced resolution instead of a gap, and
a playout-buffer simulation with low/high-water marks that shows
underruns when jitter exceeds the buffer depth.

Run:  python3 main.py
Exit: 0
"""

from __future__ import annotations

import math
import random
from typing import List, Tuple


# ---- Download-delay model ------------------------------------------------

def download_delay_seconds(file_bytes: int, link_bps: float) -> float:
    """Time to fully download a file before playback can start."""
    return file_bytes * 8 / link_bps


def download_delay_table() -> None:
    """Show why the naive download model fails for media."""
    print("=== Naive download delay before playback ===")
    cases = [
        ("4 MB MP3", 4 * 1024 * 1024, 1_000_000),
        ("4 MB MP3", 4 * 1024 * 1024, 10_000_000),
        ("700 MB movie", 700 * 1024 * 1024, 1_000_000),
        ("700 MB movie", 700 * 1024 * 1024, 10_000_000),
    ]
    print(f"{'file':>16} {'link':>10} {'delay':>10}")
    for name, size, link in cases:
        d = download_delay_seconds(size, link)
        print(f"{name:>16} {link/1e6:>8.0f} Mbps {d:>8.1f} sec")
    print("  -> metafile streaming starts after a short buffer fill, not full download.\n")


# ---- FEC parity across packets -------------------------------------------

def xor_bytes(a: bytes, b: bytes) -> bytes:
    """XOR two equal-length byte strings."""
    if len(a) != len(b):
        raise ValueError("lengths must match")
    return bytes(x ^ y for x, y in zip(a, b))


def build_parity_packet(packets: List[bytes]) -> bytes:
    """Build a parity packet as XOR of all data packets (FEC group)."""
    if not packets:
        return b""
    p = bytearray(packets[0])
    for pkt in packets[1:]:
        if len(pkt) != len(p):
            raise ValueError("all packets must be equal length")
        for i, b in enumerate(pkt):
            p[i] ^= b
    return bytes(p)


def fec_recover(received: List[bytes], parity: bytes, group_size: int) -> Tuple[bool, List[bytes]]:
    """Try to recover one lost data packet from the parity packet.

    received: list with None placeholder for the lost packet.
    Returns (success, recovered_group).
    """
    lost_idx = -1
    for i, p in enumerate(received):
        if p is None:
            if lost_idx != -1:
                return False, received  # two losses: unrecoverable
            lost_idx = i
    if lost_idx == -1:
        return True, received  # nothing lost
    # reconstruct: lost = parity XOR (all other data)
    recovered = bytearray(parity)
    for i, p in enumerate(received):
        if i == lost_idx or p is None:
            continue
        for j, b in enumerate(p):
            recovered[j] ^= b
    out = list(received)
    out[lost_idx] = bytes(recovered)
    return True, out


def fec_demo() -> None:
    """Demonstrate FEC parity across 4 packets + 1 parity."""
    print("=== FEC: parity across 4 data packets ===")
    random.seed(42)
    data = [bytes([random.randint(0, 255) for _ in range(8)]) for _ in range(4)]
    parity = build_parity_packet(data)
    print(f"  data   : {[d.hex() for d in data]}")
    print(f"  parity : {parity.hex()}  (XOR of all 4)")
    overhead = 1 / 4
    print(f"  overhead: {overhead*100:.0f}%  (5 packets for 4 data)")
    # case 1: lose one data packet
    rx = [data[0], None, data[2], data[3]]
    ok, rec = fec_recover(rx, parity, 4)
    print(f"  lose pkt 1 -> recover: {ok}, reconstructed={rec[1].hex() if ok else 'N/A'}")
    print(f"    matches original: {rec[1] == data[1]}")
    # case 2: lose two data packets
    rx2 = [None, data[1], None, data[3]]
    ok2, rec2 = fec_recover(rx2, parity, 4)
    print(f"  lose pkt 0 and 2 -> recover: {ok2}  (two erasures cannot be recovered)")
    # case 3: lose only the parity packet
    rx3 = list(data)
    ok3, _ = fec_recover(rx3, parity, 4)
    print(f"  lose parity only -> no data loss, parity not needed (ok={ok3})")
    print()


# ---- Interleaving --------------------------------------------------------

def interleave_even_odd(samples: List[float]) -> Tuple[List[float], List[float]]:
    """Split samples into even-indexed and odd-indexed packets."""
    evens = samples[0::2]
    odds = samples[1::2]
    return evens, odds


def deinterleave(evens: List[float], odds: List[float], lost_parity: bool) -> List[float]:
    """Reconstruct samples; if one of even/odd is lost, interpolate."""
    total = len(evens) + len(odds)
    out: List[float] = [0.0] * total
    for i, v in enumerate(evens):
        if 2 * i < total:
            out[2 * i] = v
    for i, v in enumerate(odds):
        if 2 * i + 1 < total:
            out[2 * i + 1] = v
    if lost_parity and len(evens) > 1:
        # pretend odds lost: interpolate odd from even neighbors
        n_odds = len(evens) - 1
        for i in range(n_odds):
            lo = evens[i]
            hi = evens[i + 1]
            if 2 * i + 1 < total:
                out[2 * i + 1] = (lo + hi) / 2.0
    return out


def interleaving_demo() -> None:
    """Show that a lost interleaved packet becomes reduced resolution."""
    print("=== Interleaving: even/odd sample separation ===")
    samples = [round(100 * math.sin(i * 0.3), 2) for i in range(20)]
    evens, odds = interleave_even_odd(samples)
    print(f"  original samples : {samples[:8]} ...")
    print(f"  even packet      : {evens[:6]} ...")
    print(f"  odd packet       : {odds[:6]} ...")
    # case A: no loss
    recon_a = deinterleave(evens, odds, lost_parity=False)
    print(f"  no loss -> exact reconstruction: {recon_a[:8] == samples[:8]}")
    # case B: odd packet lost -> interpolate
    recon_b = deinterleave(evens, [], lost_parity=True)
    print(f"  odd packet lost -> interpolated: {[round(v,2) for v in recon_b[:8]]} ...")
    err = [abs(o - r) for o, r in zip(samples, recon_b)]
    print(f"  max interpolation error: {max(err):.2f}  (reduced resolution, not a gap)")
    print()


# ---- Playout buffer simulation -------------------------------------------

def playout_buffer_sim(buffer_sec: float, jitter_ms: List[float]) -> None:
    """Simulate a playout buffer; report underruns."""
    print(f"=== Playout buffer ({buffer_sec:.1f}s startup) ===")
    # each step represents 100 ms of playout; network delivers with jitter
    level = buffer_sec * 1000.0  # ms of media in buffer
    playout_per_step = 100.0  # ms
    underruns = 0
    steps = len(jitter_ms)
    for i in range(steps):
        # network adds this much media this step (100 ms + jitter offset)
        net = max(0.0, playout_per_step + jitter_ms[i])
        level += net - playout_per_step
        if level <= 0:
            underruns += 1
            level = 0.0
    print(f"  steps={steps}, underruns={underruns}")
    print(f"  jitter range: min={min(jitter_ms):.0f}ms max={max(jitter_ms):.0f}ms")
    print(f"  -> {'buffer OK' if underruns == 0 else str(underruns) + ' underruns; increase low-water mark'}")
    print()


# ---- RTSP command table --------------------------------------------------

def rtsp_table() -> None:
    """Print the six RTSP commands."""
    print("=== RTSP commands (RFC 2326) ===")
    cmds = [
        ("DESCRIBE", "List media parameters"),
        ("SETUP", "Establish logical channel"),
        ("PLAY", "Start sending data"),
        ("RECORD", "Start accepting data"),
        ("PAUSE", "Temporarily stop sending"),
        ("TEARDOWN", "Release the logical channel"),
    ]
    for c, d in cmds:
        print(f"  {c:<10} {d}")
    print()


def main() -> None:
    print("Streaming Stored and Live Media\n")
    download_delay_table()
    fec_demo()
    interleaving_demo()
    # jitter scenarios: stored (5s buffer) vs live (10s buffer)
    random.seed(7)
    jitter = [random.gauss(0, 60) for _ in range(50)]  # +-60ms
    playout_buffer_sim(5.0, jitter)
    playout_buffer_sim(10.0, jitter)
    # extreme jitter
    big_jitter = [random.gauss(0, 500) for _ in range(50)]
    playout_buffer_sim(5.0, big_jitter)
    rtsp_table()
    print("Done. All demonstrations completed.")


if __name__ == "__main__":
    main()
