#!/usr/bin/env python3
"""ECN marking and AQM (RED/CoDel) interaction diagnostic.

Reference oracle for the integrated troubleshooting lab. Walks the
ECN state machine and the CoDel marking logic, then prints the
verdict that matches the production `tc -s qdisc` output.

Scenarios:

  ecn_marked
    CoDel is configured with the `ecn` parameter; the queue marks
    CE on congested packets; the receiver echoes ECE; the sender
    halves its CWND. Throughput collapses.

  ecn_blackhole
    A legacy middlebox strips the ECE flag from the SYN-ACK; the
    sender never knows the receiver supports ECN; the sender
    treats every data packet as Not-ECT; CoDel drops instead.

  ecn_disabled
    `net.ipv4.tcp_ecn=0` on the sender; the sender's data packets
    are Not-ECT; CoDel cannot mark and must drop.

  no_ecn_negotiated
    ECN negotiation failed in the SYN/SYN-ACK handshake; the
    sender and receiver both treat every packet as Not-ECT.

Run:  python3 main.py --scenario ecn_marked
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class EcnField:
    name: str
    bits: str  # two-bit value, e.g. "10" for ECT(0)


ECN_VALUES = {
    "00": "Not-ECT",
    "01": "ECT(1)",
    "10": "ECT(0)",
    "11": "CE",
}

# Per-byte offsets in the IP header (RFC 791) where the ECN field
# lives in the Type of Service / Differentiated Services byte.
IP_TOS_OFFSET = 1
IP_TOS_ECN_MASK = 0x03

# Per-byte offset in the TCP header (RFC 793) where the ECN-related
# flag bits (CWR, ECE) live. They occupy the two reserved bits in
# byte 13, the same byte that holds the URG/ACK/PSH/RST/SYN/FIN flags.
TCP_FLAGS_OFFSET = 13
TCP_CWR_MASK = 0x80
TCP_ECE_MASK = 0x40


def encode_ecn(bits: str) -> int:
    """Return the integer value of a two-bit ECN field encoding."""
    if bits not in ECN_VALUES:
        raise ValueError(f"unknown ECN encoding: {bits!r}")
    return int(bits, 2)


def cwr_ece_byte(ack: bool, psh: bool, cwr: bool, ece: bool) -> int:
    """Compute the TCP byte-13 value for a given combination of flags.

    The standard 6-bit field has URG/ACK/PSH/RST/SYN/FIN; CWR and ECE
    are the two reserved bits in this byte.
    """
    value = 0
    if ack:
        value |= 0x10
    if psh:
        value |= 0x08
    if cwr:
        value |= TCP_CWR_MASK
    if ece:
        value |= TCP_ECE_MASK
    return value


def parse_ecn_packet(tos_byte: int, tcp_flags_byte: int) -> tuple[str, bool, bool]:
    """Parse a packet's ECN field and TCP ECN flags.

    Returns (ecn_name, cwr_set, ece_set).
    """
    ecn_bits = f"{tos_byte & IP_TOS_ECN_MASK:02b}"
    ecn_name = ECN_VALUES[ecn_bits]
    cwr_set = bool(tcp_flags_byte & TCP_CWR_MASK)
    ece_set = bool(tcp_flags_byte & TCP_ECE_MASK)
    return (ecn_name, cwr_set, ece_set)


def feedback_expected(ecn_name: str) -> bool:
    """A CE marking is expected to produce a receiver ECE echo."""
    return ecn_name == "CE"


def cwnd_halved_on_ece(cwr_set: bool, ece_set: bool) -> bool:
    """The sender halves its CWND when it sees ECE; CWR confirms."""
    return ece_set and not cwr_set


def render_scenario(scenario: str) -> str:
    out: list[str] = []
    out.append("=" * 64)
    out.append(f"ECN / CoDel DIAGNOSTIC  --  scenario: {scenario}")
    out.append("=" * 64)
    out.append("")
    out.append("ECN field values (RFC 3168):")
    for bits, name in ECN_VALUES.items():
        out.append(f"  {bits}  = {name}")
    out.append("")
    out.append("TCP header byte 13 layout:")
    out.append("  bit: 7 6 5 4 3 2 1 0")
    out.append("       CWR ECE URG ACK PSH RST SYN FIN")
    out.append("")
    if scenario == "ecn_marked":
        out.append("tc -s qdisc show dev eth0:")
        out.append("  qdisc codel 1: root refcnt 2 limit 1000p target 5.0ms interval 100ms ecn")
        out.append("   Sent 1872345678 bytes 1500223 pkt (dropped 0, overlimits 0, ecn_mark 12045)")
        out.append("   backlog 0b 0p requeues 0")
        out.append("    count 12045 lastcount 1 ldelay 4ms drop_next 0us")
        out.append("    maxpacket 1542 ecn_mark 12045")
        out.append("")
        out.append("Wire behavior:")
        out.append("  1. Sender sets ECT(0) on every data packet (tcp_ecn=1).")
        out.append("  2. CoDel sojourn time exceeds 5ms; CE is marked in the ECN field.")
        out.append("  3. Receiver sees CE; sets ECE in next outgoing ACK.")
        out.append("  4. Sender sees ECE; halves its CWND; sets CWR in next data packet.")
        out.append("  5. Repeat every ~5s.")
        out.append("")
        out.append("Verdict: ECN feedback loop is active. Throughput drops 50% because")
        out.append("CWND is halved on each ECN feedback and slow-start is too slow to recover.")
        out.append("Fix: tc qdisc replace dev eth0 root codel target 5ms interval 100ms   (no ecn)")
    elif scenario == "ecn_blackhole":
        out.append("RFC 5562: a legacy middlebox strips the ECE flag from the SYN-ACK.")
        out.append("Sender's tcp_ecn=1: it sets ECT(0) on data packets but the receiver")
        out.append("never confirms. CoDel marks CE; the receiver's ECN feedback is ignored.")
        out.append("Verdict: the receiver falls back to Not-ECT after 1 RTT without ECE;")
        out.append("CoDel drops instead. Recovery is via loss-based congestion control.")
    elif scenario == "ecn_disabled":
        out.append("Sender's net.ipv4.tcp_ecn=0. Every data packet has ECN field = 00 (Not-ECT).")
        out.append("CoDel cannot mark CE; it must drop. Throughput suffers; recovery via")
        out.append("fast retransmit / RTO.")
        out.append("Verdict: safe path; no ECN feedback loop. Loss-based recovery only.")
    else:
        out.append("ECN negotiation in the SYN/SYN-ACK failed: receiver did not set ECE")
        out.append("in the SYN-ACK. Both sides fall back to Not-ECT.")
        out.append("Verdict: same as ecn_disabled; safe, no ECN feedback.")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--scenario",
        choices=("ecn_marked", "ecn_blackhole", "ecn_disabled", "no_ecn_negotiated"),
        default="ecn_marked",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the ECN encoder/decoder self-test and exit.",
    )
    args = parser.parse_args()
    if args.self_test:
        for bits, name in ECN_VALUES.items():
            encoded = encode_ecn(bits)
            decoded = ECN_VALUES[f"{encoded:02b}"]
            assert decoded == name, f"ECN round-trip failed for {bits}"
        syn_with_ecn = cwr_ece_byte(ack=False, psh=False, cwr=True, ece=True)
        assert syn_with_ecn & TCP_CWR_MASK, "CWR not set in SYN"
        assert syn_with_ecn & TCP_ECE_MASK, "ECE not set in SYN"
        print("ECN encoder/decoder self-test: PASS")
        return
    print(render_scenario(args.scenario))


if __name__ == "__main__":
    main()
