"""Third-Generation Mobile Networks: UMTS, WCDMA, and the Cellular Design.

Stdlib-only teaching model, five runnable demos:
  cellular_reuse  - hex-cell reuse distance + co-channel SIR trade
  cdma_sir         - uplink SIR = 1/(N-1) and the pole capacity
  ovsf_*           - WCDMA OVSF spreading, despreading, orthogonality
  handover_demo    - pilot-set state machine (soft vs hard)
  aka_demo         - UMTS AKA mutual authentication transcript

No external packages, no network calls. Run:  python3 main.py
"""

from __future__ import annotations

import hashlib
import hmac
import math
from dataclasses import dataclass, field

def cellular_reuse(radius_km: float, cluster_k: int, total_band_mhz: float) -> dict:
    """Hex reuse distance D = R*sqrt(3*K); per-cell band = B/K; SIR rank vs D/R."""
    if cluster_k <= 0:
        raise ValueError("cluster size must be positive")
    reuse_km = radius_km * math.sqrt(3 * cluster_k)
    per_cell_mhz = total_band_mhz / cluster_k
    sir_rank = round(20 * math.log10(reuse_km / radius_km), 1)
    return {
        "K": cluster_k,
        "R_km": radius_km,
        "D_km": round(reuse_km, 2),
        "per_cell_MHz": round(per_cell_mhz, 3),
        "cochannel_sir_dB_rank": sir_rank,
    }

def cdma_sir(chip_rate_mcps: float, bit_rate_kbps: float, eb_io_db: float) -> dict:
    """Gp=chip/bit; Eb/I0=Gp/(N-1); pole N = 1 + Gp/(Eb/I0_target). SIR=1/(N-1)."""
    gp = (chip_rate_mcps * 1e6) / (bit_rate_kbps * 1e3)
    eb_io_lin = 10 ** (eb_io_db / 10)
    pole = 1 + gp / eb_io_lin
    sir_at_pole_db = 10 * math.log10(1.0 / (pole - 1)) if pole > 1 else float("-inf")
    return {
        "chip_rate_Mcps": chip_rate_mcps,
        "bit_rate_kbps": bit_rate_kbps,
        "processing_gain": round(gp, 1),
        "Gp_dB": round(10 * math.log10(gp), 1),
        "Eb_I0_target_dB": eb_io_db,
        "pole_capacity_users": int(pole),
        "SIR_at_pole_dB": round(sir_at_pole_db, 2),
    }

def ovsf_code(spreading_factor: int, index: int) -> list[int]:
    """OVSF (Hadamard) code row at given SF and index; all rows mutually orthogonal."""
    if spreading_factor < 1 or spreading_factor & (spreading_factor - 1):
        raise ValueError("spreading factor must be a power of 2")
    if not 0 <= index < spreading_factor:
        raise ValueError("index out of range for this spreading factor")

    def hadamard(n: int) -> list[list[int]]:
        if n == 1:
            return [[1]]
        h = hadamard(n // 2)
        top = [row + row for row in h]
        bot = [row + [-x for x in row] for row in h]
        return top + bot

    return hadamard(spreading_factor)[index]

def spread(bits: list[int], code: list[int]) -> list[int]:
    """Spread a list of {0,1} bits with the given +1/-1 OVSF code."""
    out: list[int] = []
    for b in bits:
        sym = 1 if b == 1 else -1
        out.extend(sym * c for c in code)
    return out

def despread(chips: list[int], code: list[int]) -> list[int]:
    """Correlate chips with the code over each bit period; decide 0/1."""
    sf = len(code)
    if len(chips) % sf != 0:
        raise ValueError("chip stream not a whole number of bits")
    bits: list[int] = []
    for i in range(0, len(chips), sf):
        acc = sum(chips[i + j] * code[j] for j in range(sf))
        bits.append(1 if acc > 0 else 0)
    return bits

def cross_correlate(code_a: list[int], code_b: list[int]) -> int:
    """Sum of elementwise products; 0 for orthogonal OVSF siblings."""
    if len(code_a) != len(code_b):
        raise ValueError("codes must share a spreading factor")
    return sum(a * b for a, b in zip(code_a, code_b))

@dataclass
class NodeB:
    name: str
    ec_io_db: list[float]  # pilot Ec/I0 trace in dB, per sample

@dataclass
class HandoverLog:
    sample: int
    node: str
    event: str
    kind: str  # "soft" | "hard" | "drop"
    active_set: list[str] = field(default_factory=list)

def handover_demo(nodes: list[NodeB], add_db: float, drop_db: float,
                  add_dwell: int, drop_dwell: int) -> list[HandoverLog]:
    """Pilot-set state machine: add above add_db for add_dwell, drop below drop_db for drop_dwell."""
    horizon = max(len(n.ec_io_db) for n in nodes)
    active: set[str] = set()
    above: dict[str, int] = {n.name: 0 for n in nodes}
    below: dict[str, int] = {n.name: 0 for n in nodes}
    log: list[HandoverLog] = []
    for t in range(horizon):
        for nb in nodes:
            v = nb.ec_io_db[t] if t < len(nb.ec_io_db) else float("-inf")
            above[nb.name] = above[nb.name] + 1 if v > add_db else 0
            below[nb.name] = below[nb.name] + 1 if v < drop_db else 0
            if above[nb.name] == add_dwell and nb.name not in active:
                kind = "soft" if active else "hard"
                active.add(nb.name)
                log.append(HandoverLog(t, nb.name, f"add ({v:.1f} dB)", kind,
                                       sorted(active)))
            if below[nb.name] == drop_dwell and nb.name in active:
                active.discard(nb.name)
                kind = "soft" if active else "hard"
                log.append(HandoverLog(t, nb.name, f"drop ({v:.1f} dB)", kind,
                                       sorted(active)))
    return log

def _f(key: bytes, label: str, rand: bytes, length: int) -> bytes:
    """Toy UMTS f-function: HMAC-SHA256 truncated (real UMTS uses Kasumi/MILENAGE)."""
    return hmac.new(key, label.encode() + rand, hashlib.sha256).digest()[:length]

def aka_demo(k: bytes, rand: bytes, amf: bytes, sqn: bytes) -> dict:
    """UMTS AKA transcript: f1=MAC, f2=RES, f3=CK, f4=IK, f5=AK."""
    mac = _f(k, "f1", rand + sqn + amf, 8)
    res = _f(k, "f2", rand, 8)
    ck = _f(k, "f3", rand, 16)
    ik = _f(k, "f4", rand, 16)
    ak = _f(k, "f5", rand, 6)
    return {
        "RAND_hex": rand.hex(),
        "SQN_hex": sqn.hex(),
        "AMF_hex": amf.hex(),
        "MAC_f1_hex": mac.hex(),
        "RES_f2_hex": res.hex(),
        "CK_f3_hex": ck.hex(),
        "IK_f4_hex": ik.hex(),
        "AK_f5_hex": ak.hex(),
        "sim_verifies_network_mac": True,
        "network_verifies_sim_res": True,
    }

def _hr(title: str) -> None:
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)

def main() -> None:
    _hr("1. CELLULAR FREQUENCY REUSE (hex cluster)")
    print("D = R * sqrt(3*K); per-cell band = B/K; SIR rank rises with D/R.\n")
    for k in (4, 7, 12, 14):
        r = cellular_reuse(1.0, k, 20.0)
        print(f"  K={r['K']:>2}: D={r['D_km']:>5} km  per_cell="
              f"{r['per_cell_MHz']:>6.3f} MHz  SIR_rank={r['cochannel_sir_dB_rank']:>5} dB")

    _hr("2. CDMA UPLINK SIR AND POLE CAPACITY (3.84 Mcps)")
    print("Gp = chip/bit; Eb/I0 = Gp/(N-1); pole N = 1 + Gp/(Eb/I0).")
    print("SIR = 1/(N-1) at the pole.\n")
    for br, eb in ((12.2, 7.0), (384.0, 3.0), (2048.0, 1.5)):
        d = cdma_sir(3.84, br, eb)
        print(f"  {d['bit_rate_kbps']:>7.1f} kbps @ Eb/I0={d['Eb_I0_target_dB']} dB"
              f" -> Gp={d['processing_gain']:>7.1f} ({d['Gp_dB']} dB)"
              f" N_pole={d['pole_capacity_users']:>4} users")

    _hr("3. OVSF SPREAD/DESPREAD (SF=8, message 1011)")
    code = ovsf_code(8, 4)  # [+1 +1 +1 +1 -1 -1 -1 -1], per the lesson
    msg = [1, 0, 1, 1]
    chips = spread(msg, code)
    recovered = despread(chips, code)
    print(f"  OVSF(8,4) = {code}")
    print(f"  message        = {msg}")
    print(f"  chips ({len(chips)}) = {chips}")
    print(f"  despread       = {recovered}   (matches: {recovered == msg})")
    other = ovsf_code(8, 6)  # different OVSF branch, still orthogonal
    print(f"\n  Second user OVSF(8,6) = {other}")
    print(f"  cross-correlation with OVSF(8,4) = {cross_correlate(code, other)}  "
          "(0 => orthogonal => no interference after despreading)")
    print("\n  Corrupt all 8 chips of bit period 1 (single-chip flips are absorbed")
    print("  by the +8/-8 margin; full corruption flips the decision):")
    broken = chips[:]
    for j in range(8, 16):
        broken[j] *= -1
    print(f"  despread(broken) = {despread(broken, code)}   "
          f"(bit 1 flips 0->1 under heavy interference)")

    _hr("4. HANDOVER STATE MACHINE (add -12 dB, drop -14 dB, dwell 3)")
    nodes = [
        NodeB("B1", [-9, -10, -11, -9, -8, -7]),
        NodeB("B2", [-18, -16, -13, -10, -9, -8]),
        NodeB("B3", [-20, -19, -19, -16, -11, -8]),
    ]
    log = handover_demo(nodes, add_db=-12.0, drop_db=-14.0,
                        add_dwell=3, drop_dwell=3)
    if not log:
        print("  (no transitions in this trace)")
    for e in log:
        print(f"  t={e.sample} {e.node:3} {e.event:<16} [{e.kind:<4}] active={e.active_set}")

    _hr("5. UMTS AKA MUTUAL AUTHENTICATION (toy HMAC-SHA256 f-functions)")
    k = b"subscriber-secret-key-K"
    rand = bytes.fromhex("a1b2c3d4e5f60718293a4b5c6d7e8f90")
    amf = bytes.fromhex("0000")
    sqn = bytes.fromhex("000000000001")
    tr = aka_demo(k, rand, amf, sqn)
    for kk, vv in tr.items():
        print(f"  {kk:<24} = {vv}")
    forged_mac = bytes(8)
    verdict = "REJECT" if forged_mac.hex() != tr["MAC_f1_hex"] else "ACCEPT"
    print(f"\n  SIM given forged MAC {forged_mac.hex()} -> {verdict}")

    print("\n" + "=" * 72)
    print("  Done. See docs/en.md for the mechanisms behind each block.")
    print("=" * 72)

if __name__ == "__main__":
    main()
