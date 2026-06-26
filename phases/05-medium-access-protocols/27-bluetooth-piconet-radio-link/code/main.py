"""bluetooth_piconet.py — Bluetooth FHSS hop sequence, AFH simulation, and
frame-header majority-vote decoding.

Implements the core mechanisms from the lesson:
  * Pseudorandom FHSS hop sequence derived from BD_ADDR (LCG seed)
  * Wi-Fi / Bluetooth channel overlap computation (22 MHz 802.11 bandwidth)
  * Adaptive Frequency Hopping (AFH): exclude bad channels, require ≥20 remain
  * Collision-rate measurement: fixed FHSS vs AFH
  * Bluetooth frame efficiency for 1-/3-/5-slot frames at 1 Mbps
  * Frame header builder + 3× repetition encoder + majority-vote decoder
  * SCO voice link capacity (64 kbps from 80-bit PCM × 800 slots/sec)
  * TDM slot schedule for a piconet with N active slaves

No external dependencies. Run: python3 code/main.py
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Physical / protocol constants
# ---------------------------------------------------------------------------

TOTAL_CHANNELS: int = 79        # Bluetooth channels 0–78 (2.402–2.480 GHz)
SLOT_US: int = 625              # µs per slot (= 625 bits at 1 Mbps)
SLOT_BITS: int = SLOT_US        # bits per slot at 1 Mbps
BIT_RATE_MBPS: int = 1
ACCESS_CODE_BITS: int = 72
HEADER_RAW_BITS: int = 18       # Addr(3)+Type(4)+Flow(1)+ARQN(1)+SEQN(1)+HEC(8)
HEADER_CODED_BITS: int = HEADER_RAW_BITS * 3   # 54 bits after 3× repetition
SETTLING_US: int = 250          # radio oscillator settling time per frame (µs)
HOPS_PER_SEC: int = 1600        # maximum hop rate

# SCO voice link parameters
SCO_PAYLOAD_BITS: int = 80      # 80-bit PCM payload per slot per direction


# ---------------------------------------------------------------------------
# Hop-sequence generator (LCG — pedagogical substitute for real BT algorithm)
# ---------------------------------------------------------------------------

def bd_addr_to_seed(bd_addr_hex: str) -> int:
    """Convert a BD_ADDR string like '00:1A:7D:DA:71:13' to a 48-bit integer."""
    return int(bd_addr_hex.replace(":", ""), 16)


def _lcg_step(state: int) -> int:
    """One step of the Knuth/Numerical-Recipes multiplicative LCG, 32-bit."""
    return (state * 1_664_525 + 1_013_904_223) & 0xFFFF_FFFF


def fixed_hop_sequence(seed: int, n_hops: int) -> list[int]:
    """Pseudorandom hop sequence across all 79 channels (Bluetooth 1.0/1.1)."""
    hops: list[int] = []
    state = seed & 0xFFFF_FFFF
    for _ in range(n_hops):
        state = _lcg_step(state)
        hops.append(state % TOTAL_CHANNELS)
    return hops


def afh_hop_sequence(seed: int, bad_channels: set[int], n_hops: int) -> list[int]:
    """AFH hop sequence excluding bad channels (Bluetooth 1.2+).

    Returns an empty list if fewer than 20 good channels remain
    (regulatory minimum per the Bluetooth spec).
    """
    good = [ch for ch in range(TOTAL_CHANNELS) if ch not in bad_channels]
    if len(good) < 20:
        return []          # regulatory minimum not met; AFH cannot operate
    hops: list[int] = []
    state = seed & 0xFFFF_FFFF
    for _ in range(n_hops):
        state = _lcg_step(state)
        hops.append(good[state % len(good)])
    return hops


# ---------------------------------------------------------------------------
# Wi-Fi / Bluetooth channel overlap
# ---------------------------------------------------------------------------

def wifi_occupied_channels(wifi_channels: list[int]) -> set[int]:
    """Return Bluetooth channels (0–78) that overlap any 802.11 channel.

    802.11 channel k is centred at (2407 + 5k) MHz with ±11 MHz half-bandwidth.
    Bluetooth channel b is centred at (2402 + b) MHz with 1 MHz bandwidth.
    Overlap when |bt_centre − wifi_centre| ≤ 11 MHz.
    """
    occupied: set[int] = set()
    for wifi_ch in wifi_channels:
        wifi_centre = 2407 + 5 * wifi_ch
        for bt_ch in range(TOTAL_CHANNELS):
            bt_centre = 2402 + bt_ch
            if abs(bt_centre - wifi_centre) <= 11:
                occupied.add(bt_ch)
    return occupied


def collision_rate(hop_seq: list[int], bad_channels: set[int]) -> float:
    """Fraction of hops that land on a bad (occupied) channel."""
    if not hop_seq:
        return 0.0
    return sum(1 for h in hop_seq if h in bad_channels) / len(hop_seq)


# ---------------------------------------------------------------------------
# Frame efficiency
# ---------------------------------------------------------------------------

def frame_efficiency(payload_bits: int, slot_count: int = 1) -> float:
    """Payload efficiency = payload_bits / total_slot_bits (1-/3-/5-slot)."""
    return payload_bits / (SLOT_BITS * slot_count)


def overhead_breakdown(slot_count: int = 1) -> dict[str, float]:
    """Return fraction of capacity consumed by each overhead component."""
    total_bits = float(SLOT_BITS * slot_count)
    return {
        "settling_time": SETTLING_US / total_bits,
        "access_code":   ACCESS_CODE_BITS / total_bits,
        "header_3x":     HEADER_CODED_BITS / total_bits,
    }


# ---------------------------------------------------------------------------
# Bluetooth frame header: build, 3× encode, majority-vote decode
# ---------------------------------------------------------------------------

@dataclass
class BluetoothHeader:
    """Decoded fields of the 18-bit Bluetooth frame header.

    Bit layout: [Addr 3][Type 4][Flow 1][ARQN 1][SEQN 1][HEC 8] = 18 bits.
    """
    addr: int      # 3-bit slave address (0 = broadcast, 1–7 = unicast)
    pkt_type: int  # 4-bit packet type
    flow: int      # 1-bit: slave buffer full flag
    arqn: int      # 1-bit: piggybacked ACK(1) / NAK(0)
    seqn: int      # 1-bit: stop-and-wait sequence number
    hec: int       # 8-bit header error check


def build_header_bits(hdr: BluetoothHeader) -> int:
    """Pack header fields into an 18-bit integer (MSB = addr[2])."""
    return (
        ((hdr.addr     & 0x07) << 15) |
        ((hdr.pkt_type & 0x0F) << 11) |
        ((hdr.flow     & 0x01) << 10) |
        ((hdr.arqn    & 0x01) <<  9) |
        ((hdr.seqn    & 0x01) <<  8) |
        (hdr.hec & 0xFF)
    )


def encode_3x_repetition(raw18: int) -> int:
    """Repeat the 18-bit header three times to produce a 54-bit coded word."""
    return (raw18 << 36) | (raw18 << 18) | raw18


def inject_bit_errors(coded54: int, error_positions: list[int]) -> int:
    """Flip specified bit positions in the 54-bit coded word."""
    for pos in error_positions:
        coded54 ^= (1 << pos)
    return coded54


def majority_vote_decode(coded54: int) -> int:
    """Recover an 18-bit header from a (possibly corrupted) 54-bit coded word.

    For each bit position, take the majority of the three copies.
    This corrects any single-copy corruption on any bit.
    """
    copy0 = (coded54 >> 36) & 0x3FFFF
    copy1 = (coded54 >> 18) & 0x3FFFF
    copy2 =  coded54        & 0x3FFFF

    recovered = 0
    for bit in range(18):
        b0 = (copy0 >> bit) & 1
        b1 = (copy1 >> bit) & 1
        b2 = (copy2 >> bit) & 1
        majority = 1 if (b0 + b1 + b2) >= 2 else 0
        recovered |= majority << bit
    return recovered


def parse_header_bits(raw18: int) -> BluetoothHeader:
    """Unpack an 18-bit integer into a BluetoothHeader."""
    return BluetoothHeader(
        addr     = (raw18 >> 15) & 0x07,
        pkt_type = (raw18 >> 11) & 0x0F,
        flow     = (raw18 >> 10) & 0x01,
        arqn     = (raw18 >>  9) & 0x01,
        seqn     = (raw18 >>  8) & 0x01,
        hec      =  raw18        & 0xFF,
    )


# ---------------------------------------------------------------------------
# TDM slot scheduler (piconet)
# ---------------------------------------------------------------------------

def piconet_slot_schedule(n_slaves: int, n_slots: int) -> list[str]:
    """Generate TDM slot labels for a piconet with n_slaves active slaves.

    Even slots: master transmits to a slave (round-robin over slaves).
    Odd slots:  that slave transmits back to master.
    """
    schedule: list[str] = []
    slave_idx = 0
    for slot in range(n_slots):
        current_slave = (slave_idx % n_slaves) + 1
        if slot % 2 == 0:   # even: master → slave
            schedule.append(f"M→S{current_slave}")
        else:               # odd: slave → master
            schedule.append(f"S{current_slave}→M")
            slave_idx += 1  # advance to next slave after each full exchange
    return schedule


# ---------------------------------------------------------------------------
# SCO link capacity
# ---------------------------------------------------------------------------

def sco_capacity_bps() -> dict[str, float]:
    """Calculate SCO link capacity (800 slots/sec × 80 bits = 64 000 bps)."""
    slots_per_sec_per_dir = 1_000_000 // (SLOT_US * 2)   # 800 slots/sec
    capacity_bps = slots_per_sec_per_dir * SCO_PAYLOAD_BITS
    raw_half_bps = (BIT_RATE_MBPS * 1_000_000) / 2
    return {
        "slots_per_sec": slots_per_sec_per_dir,
        "capacity_bps":  capacity_bps,
        "raw_half_bps":  raw_half_bps,
        "efficiency":    capacity_bps / raw_half_bps,
    }


# ---------------------------------------------------------------------------
# Main demonstration
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(title)
    print(f"{'─' * 60}")


def main() -> None:
    master_addr = "00:1A:7D:DA:71:13"
    seed = bd_addr_to_seed(master_addr)
    n_hops = HOPS_PER_SEC          # 1 second of hops

    print("=" * 60)
    print("Bluetooth Piconet — FHSS / AFH / Frame Simulation")
    print("=" * 60)
    print(f"  Master BD_ADDR : {master_addr}")
    print(f"  Seed (48-bit)  : 0x{seed:012X}")
    print(f"  Simulation     : {n_hops} hops ({n_hops / HOPS_PER_SEC:.1f} s "
          f"at {HOPS_PER_SEC} hops/sec)")

    # ------------------------------------------------------------------
    # 1. Wi-Fi channel overlap computation
    # ------------------------------------------------------------------
    section("1. Wi-Fi / Bluetooth channel overlap map (802.11 ±11 MHz per channel)")

    # Single Wi-Fi channel scenario (common office: only ch6 nearby)
    wifi_single = [6]
    bad_single = wifi_occupied_channels(wifi_single)
    good_single = TOTAL_CHANNELS - len(bad_single)
    print(f"  Single channel: 802.11 ch6 (centre 2437 MHz)")
    print(f"    Blocked BT channels : {len(bad_single)} / {TOTAL_CHANNELS}")
    print(f"    Blocked range       : {sorted(bad_single)[0]}–{sorted(bad_single)[-1]}")
    print(f"    Good channels left  : {good_single}  "
          f"(AFH minimum 20: {'OK' if good_single >= 20 else 'FAIL'})")

    # Three non-overlapping US Wi-Fi channels (saturated office)
    wifi_triple = [1, 6, 11]
    bad_triple = wifi_occupied_channels(wifi_triple)
    good_triple = TOTAL_CHANNELS - len(bad_triple)
    print(f"\n  Triple channel: 802.11 ch1, ch6, ch11 (US non-overlapping set)")
    print(f"    Each 22 MHz wide → ±11 MHz exclusion zone per channel")
    print(f"    Blocked BT channels : {len(bad_triple)} / {TOTAL_CHANNELS}  "
          f"({len(bad_triple)/TOTAL_CHANNELS:.0%} of band)")
    print(f"    Good channels left  : {good_triple}  "
          f"(AFH minimum 20: {'OK' if good_triple >= 20 else 'FAIL — AFH cannot operate'})")

    # ------------------------------------------------------------------
    # 2. Fixed FHSS collision rate (Bluetooth 1.0/1.1)
    # ------------------------------------------------------------------
    section("2. Fixed FHSS collision rate (Bluetooth 1.0/1.1)")

    fixed_hops = fixed_hop_sequence(seed, n_hops)

    cr_single = collision_rate(fixed_hops, bad_single)
    cr_triple = collision_rate(fixed_hops, bad_triple)

    print(f"  Wi-Fi ch6 only   : collision rate = {cr_single:.1%}  "
          f"(expected ~{len(bad_single)/TOTAL_CHANNELS:.1%})")
    print(f"  Wi-Fi ch1,6,11   : collision rate = {cr_triple:.1%}  "
          f"(expected ~{len(bad_triple)/TOTAL_CHANNELS:.1%})")
    print(f"\n  At {HOPS_PER_SEC} hops/sec with ch1,6,11:")
    print(f"    ~{cr_triple * HOPS_PER_SEC:.0f} slot collisions/sec")
    print(f"    Each destroys one 625 µs slot; on SCO: audio dropout (no retransmit)")

    # ------------------------------------------------------------------
    # 3. Adaptive Frequency Hopping (Bluetooth 1.2+)
    # ------------------------------------------------------------------
    section("3. Adaptive Frequency Hopping — AFH (Bluetooth 1.2+)")

    afh_hops_single = afh_hop_sequence(seed, bad_single, n_hops)
    cr_afh_single = collision_rate(afh_hops_single, bad_single)

    print(f"  Single Wi-Fi channel scenario (ch6 blocked):")
    print(f"    Good channels  : {good_single}  ≥ 20 minimum — AFH operational")
    print(f"    AFH hop count  : {len(afh_hops_single)} hops generated")
    print(f"    Collision rate : {cr_afh_single:.1%}  "
          f"(target 0%; improvement: "
          f"{(cr_single - cr_afh_single) * HOPS_PER_SEC:.0f} fewer/sec)")

    # Demonstrate the three-channel edge case
    afh_hops_triple = afh_hop_sequence(seed, bad_triple, n_hops)
    if not afh_hops_triple:
        print(f"\n  Three Wi-Fi channel scenario (ch1,6,11 blocked):")
        print(f"    Good channels : {good_triple}  < 20 minimum")
        print(f"    AFH result    : CANNOT OPERATE — regulatory minimum violated")
        print(f"    Real fix      : use 5 GHz Wi-Fi or Bluetooth 5.x with 2 Mbps PHY")

    # ------------------------------------------------------------------
    # 4. Frame efficiency table
    # ------------------------------------------------------------------
    section("4. Bluetooth frame efficiency (1 Mbps basic rate)")

    frame_configs = [
        (1, SCO_PAYLOAD_BITS, "SCO voice (PCM)"),
        (1, 240,              "1-slot ACL DM1 max"),
        (3, 1496,             "3-slot ACL DM3 max"),
        (5, 2744,             "5-slot ACL DM5 max"),
    ]
    print(f"  {'Slots':>5}  {'Payload':>8}  {'Total bits':>10}  "
          f"{'Efficiency':>10}  Type")
    print(f"  {'─'*5}  {'─'*8}  {'─'*10}  {'─'*10}  {'─'*22}")
    for slots, payload, label in frame_configs:
        eff = frame_efficiency(payload, slots)
        total = SLOT_BITS * slots
        print(f"  {slots:>5}  {payload:>8}  {total:>10}  "
              f"{eff:>9.1%}  {label}")

    # Overhead breakdown for single-slot frame
    ovhd = overhead_breakdown(1)
    print(f"\n  Single-slot (625 bits) overhead breakdown:")
    print(f"    Settling time   : {ovhd['settling_time']:.1%}  ({SETTLING_US} bits)")
    print(f"    Access code     : {ovhd['access_code']:.1%}  ({ACCESS_CODE_BITS} bits)")
    print(f"    Header (3×)     : {ovhd['header_3x']:.1%}  ({HEADER_CODED_BITS} bits)")
    total_ovhd = sum(ovhd.values())
    print(f"    Total overhead  : {total_ovhd:.1%}  →  payload fraction ≈ "
          f"{1 - total_ovhd:.1%}")
    print(f"    SCO voice uses {SCO_PAYLOAD_BITS}/{SLOT_BITS} bits ≈ "
          f"{SCO_PAYLOAD_BITS/SLOT_BITS:.1%} of slot bits")

    # ------------------------------------------------------------------
    # 5. Frame header: build → 3× encode → corrupt → majority-vote decode
    # ------------------------------------------------------------------
    section("5. Header encoding: 3× repetition + majority-vote decode")

    # Build a realistic header: slave 3, packet type 3 (DM1/ACL), ARQN=1, SEQN=0
    hdr = BluetoothHeader(addr=3, pkt_type=3, flow=0, arqn=1, seqn=0, hec=0xA7)
    raw18 = build_header_bits(hdr)
    coded54 = encode_3x_repetition(raw18)

    print(f"  Original 18-bit header : 0x{raw18:05X}  (bin: {raw18:018b})")
    print(f"  Fields : Addr={hdr.addr}  Type={hdr.pkt_type}  "
          f"Flow={hdr.flow}  ARQN={hdr.arqn}  SEQN={hdr.seqn}  HEC=0x{hdr.hec:02X}")
    print(f"  3× coded (54 bits)     : 0x{coded54:014X}")
    print(f"    copy 0 (bits 53–36)  : {(coded54>>36)&0x3FFFF:018b}")
    print(f"    copy 1 (bits 35–18)  : {(coded54>>18)&0x3FFFF:018b}")
    print(f"    copy 2 (bits 17– 0)  : {coded54&0x3FFFF:018b}")

    # Corrupt one entire copy (bits 20, 25, 30 — all within copy 1, bits 18–35)
    error_positions = [20, 25, 30]
    corrupted = inject_bit_errors(coded54, error_positions)
    print(f"\n  Injected errors at bit positions {error_positions} (within copy 1):")
    print(f"  Corrupted word         : 0x{corrupted:014X}")
    print(f"    copy 1 corrupted     : {(corrupted>>18)&0x3FFFF:018b}  ← errors here")

    recovered18 = majority_vote_decode(corrupted)
    decoded = parse_header_bits(recovered18)
    match = recovered18 == raw18

    print(f"\n  Majority-vote result   : 0x{recovered18:05X}  — "
          f"{'MATCHES original  (error corrected)' if match else 'MISMATCH  (correction failed)'}")
    print(f"  Decoded : Addr={decoded.addr}  Type={decoded.pkt_type}  "
          f"Flow={decoded.flow}  ARQN={decoded.arqn}  SEQN={decoded.seqn}  "
          f"HEC=0x{decoded.hec:02X}")

    # Show that two corrupted copies defeat majority vote
    error_positions_2copies = [20, 20 + 18]  # same bit in copies 1 and 2
    corrupted2 = inject_bit_errors(coded54, error_positions_2copies)
    recovered_fail = majority_vote_decode(corrupted2)
    print(f"\n  Two-copy corruption (same bit in copies 1 & 2): "
          f"{'CORRECTED' if recovered_fail == raw18 else 'CANNOT CORRECT — expected'}")

    # ------------------------------------------------------------------
    # 6. TDM slot schedule
    # ------------------------------------------------------------------
    section("6. Piconet TDM slot schedule (3 active slaves, 12 slots)")

    schedule = piconet_slot_schedule(n_slaves=3, n_slots=12)
    for i, label in enumerate(schedule):
        kind = "even (Master TX)" if i % 2 == 0 else "odd  (Slave TX) "
        print(f"  Slot {i:2d}  [{kind}] : {label}")

    # ------------------------------------------------------------------
    # 7. SCO voice link capacity
    # ------------------------------------------------------------------
    section("7. SCO voice link capacity")

    sco = sco_capacity_bps()
    print(f"  Slots per sec per direction : {sco['slots_per_sec']:.0f}")
    print(f"  PCM payload per slot        : {SCO_PAYLOAD_BITS} bits")
    print(f"  Voice channel capacity      : "
          f"{sco['slots_per_sec']:.0f} × {SCO_PAYLOAD_BITS} = "
          f"{sco['capacity_bps']:.0f} bps = 64 kbps")
    print(f"  Raw rate (one direction)    : {sco['raw_half_bps']/1000:.0f} kbps")
    print(f"  Efficiency                  : {sco['efficiency']:.1%} ≈ 13%")
    print(f"  Max SCO links per slave     : 3  (= 3 simultaneous voice calls)")
    print(f"  Retransmission on SCO       : NEVER — lost slots mean audio dropout")
    print(f"  ACL link retransmission     : stop-and-wait ARQ (1-bit SEQN, ARQN)")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(f"\n{'=' * 60}")
    print("Summary of results")
    print(f"{'=' * 60}")
    print(f"  Fixed FHSS (ch6)     : {cr_single:.1%} collision rate")
    print(f"  Fixed FHSS (ch1,6,11): {cr_triple:.1%} collision rate")
    print(f"  AFH (ch6 excluded)   : {cr_afh_single:.1%} collision rate  (0 collisions/sec)")
    print(f"  AFH (ch1,6,11)       : cannot operate ({good_triple} good channels < 20 min)")
    print(f"  SCO efficiency       : {sco['efficiency']:.1%}")
    print(f"  5-slot ACL efficiency: {frame_efficiency(2744, 5):.1%}")
    print(f"  Header majority-vote : {'PASS' if match else 'FAIL'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
