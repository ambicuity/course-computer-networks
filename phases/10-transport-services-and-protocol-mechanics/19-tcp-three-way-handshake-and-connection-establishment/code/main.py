#!/usr/bin/env python3
"""TCP three-way handshake simulator.

Models the three-segment open, the simultaneous-open edge case,
SYN cookies for flood defense (RFC 4987), and the SYN retransmission
backoff schedule (RFC 6298).

No network calls, no third-party packages -- pure stdlib so it runs
anywhere with `python3 main.py`.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass


SYN = 0x02
ACK = 0x10
SYN_ACK = SYN | ACK

INITIAL_BACKOFF_SEC = 1.0
MAX_BACKOFF_SEC = 64.0
MAX_SYN_ATTEMPTS = 9
TOTAL_TIMEOUT_SEC = 75.0


@dataclass(frozen=True)
class Segment:
    src: str
    dst: str
    seq: int
    ack: int
    flags: int
    payload: bytes = b""
    cookie_secret: bytes = b""

    def flag_names(self) -> str:
        names: list[str] = []
        if self.flags & SYN:
            names.append("SYN")
        if self.flags & ACK:
            names.append("ACK")
        return "+".join(names) if names else "<no flags>"


def handshake_normal(client_isn: int, server_isn: int) -> list[Segment]:
    """Return the three segments of a normal TCP open."""
    return [
        Segment("client", "server", seq=client_isn, ack=0, flags=SYN),
        Segment("server", "client", seq=server_isn, ack=client_isn + 1, flags=SYN_ACK),
        Segment("client", "server", seq=client_isn + 1, ack=server_isn + 1, flags=ACK),
    ]


def handshake_simultaneous_open(a_isn: int, b_isn: int) -> list[Segment]:
    """Both sides send SYN before receiving the peer's. Resolves in 4 segments."""
    return [
        Segment("A", "B", seq=a_isn, ack=0, flags=SYN),
        Segment("B", "A", seq=b_isn, ack=0, flags=SYN),
        Segment("A", "B", seq=a_isn + 1, ack=b_isn + 1, flags=SYN_ACK),
        Segment("B", "A", seq=b_isn + 1, ack=a_isn + 1, flags=SYN_ACK),
    ]


def cookie_value(
    client: tuple[str, int],
    server: tuple[str, int],
    mss_index: int,
    timestamp_low5: int,
    secret: bytes,
) -> int:
    """SYN-cookie generator (RFC 4987).

    32 bits total: 5 timestamp bits | 3 MSS-index bits | 24-bit HMAC prefix.
    """
    if not 0 <= mss_index < 8:
        raise ValueError("mss_index must fit in 3 bits (0..7)")
    if not 0 <= timestamp_low5 < 32:
        raise ValueError("timestamp_low5 must fit in 5 bits")
    msg = (
        client[0].encode() + str(client[1]).encode() + b"|"
        + server[0].encode() + str(server[1]).encode() + b"|"
        + bytes([mss_index, timestamp_low5])
    )
    digest = hmac.new(secret, msg, hashlib.sha256).digest()
    hmac_prefix = int.from_bytes(digest[:3], "big") & 0xFFFFFF
    cookie = (timestamp_low5 << 27) | (mss_index << 24) | hmac_prefix
    return cookie & 0xFFFFFFFF


def validate_cookie(
    ack: int,
    client: tuple[str, int],
    server: tuple[str, int],
    mss_index: int,
    timestamp_low5: int,
    secret: bytes,
) -> bool:
    """Check whether the third ACK carries a valid SYN cookie."""
    expected = cookie_value(client, server, mss_index, timestamp_low5, secret)
    return ack == (expected + 1) & 0xFFFFFFFF


def retransmit_schedule() -> list[float]:
    """Return the SYN retransmission times in seconds (RFC 6298, Linux defaults)."""
    schedule: list[float] = []
    delay = INITIAL_BACKOFF_SEC
    elapsed = 0.0
    while len(schedule) < MAX_SYN_ATTEMPTS and elapsed < TOTAL_TIMEOUT_SEC:
        schedule.append(round(delay, 3))
        elapsed += delay
        delay = min(delay * 2.0, MAX_BACKOFF_SEC)
    return schedule


def decode_syn_options(raw: bytes) -> list[tuple[str, bytes]]:
    """Walk a TCP option TLV stream and return (kind_name, value) pairs."""
    out: list[tuple[str, bytes]] = []
    i = 0
    while i < len(raw):
        kind = raw[i]
        if kind == 0:
            out.append(("EOL", b""))
            break
        if kind == 1:
            out.append(("NOP", b""))
            i += 1
            continue
        length = raw[i + 1]
        value = raw[i + 2 : i + length]
        name = {
            2: "MSS",
            3: "WSCALE",
            4: "SACK-PERMITTED",
            5: "SACK",
            8: "TIMESTAMP",
            34: "TFO-COOKIE",
        }.get(kind, f"OPT-{kind}")
        out.append((name, value))
        i += length
    return out


def show_handshake(label: str, segs: list[Segment]) -> None:
    print(f"\n  {label}")
    for idx, seg in enumerate(segs, 1):
        print(
            f"    {idx}. {seg.src} -> {seg.dst}  "
            f"flags={seg.flag_names():<8}  SEQ={seg.seq:<11}  ACK={seg.ack}"
        )


def main() -> None:
    print("=" * 70)
    print("TCP THREE-WAY HANDSHAKE  --  open, simultaneous open, SYN cookies")
    print("=" * 70)

    show_handshake("Normal three-way handshake:", handshake_normal(client_isn=100000, server_isn=200000))

    show_handshake(
        "Simultaneous open (both sides SYN_SENT before receiving peer SYN):",
        handshake_simultaneous_open(a_isn=300000, b_isn=400000),
    )

    print("\nSYN retransmission timeline (RFC 6298 / Linux defaults):")
    schedule = retransmit_schedule()
    elapsed = 0.0
    for idx, delay in enumerate(schedule, 1):
        print(f"   attempt {idx}: retransmit at t = {elayed + delay:>6.1f}s   (delay {delay:>4.1f}s)")
        elapsed += delay
    print(f"   give up after {MAX_SYN_ATTEMPTS} attempts (~{elapsed:.0f}s total)")

    print("\nSYN cookie (RFC 4987) -- no server state needed:")
    secret = b"shared-server-secret-32-bytes!!"
    client = ("203.0.113.5", 49152)
    server = ("198.51.100.10", 80)
    mss_index = 4  # 1460 in the IETF index table
    timestamp = int(time.time()) & 0x1F
    cookie = cookie_value(client, server, mss_index, timestamp, secret)
    print(f"   computed ISN (cookie) = 0x{cookie:08x}")
    third_ack = (cookie + 1) & 0xFFFFFFFF
    print(f"   client returns        ACK = ISN + 1 = 0x{third_ack:08x}")
    valid = validate_cookie(third_ack, client, server, mss_index, timestamp, secret)
    print(f"   server validates      : {valid}")
    forged = validate_cookie(third_ack + 1, client, server, mss_index, timestamp, secret)
    print(f"   forged ack rejected   : {not forged}")

    print("\nDecoded SYN options (modern Linux SYN):")
    raw = bytes.fromhex("020405b40303070402080a000123450000abcd010101")
    for name, value in decode_syn_options(raw):
        text = value.hex() if value else "(empty)"
        print(f"   {name:<14} length={len(value)}  data={text}")

    print("\nDone. Run tcpdump -i any -nn 'tcp[tcpflags] & tcp-syn != 0' to compare.")


if __name__ == "__main__":
    main()