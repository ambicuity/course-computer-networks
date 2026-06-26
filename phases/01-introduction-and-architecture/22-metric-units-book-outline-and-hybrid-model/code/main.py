"""Metric Units and the Hybrid Reference Model.

A stdlib-only toolkit for the two unit conventions that bedevil networking
capacity maths, plus a classifier that maps a problem description onto the
five-layer hybrid reference model used throughout the book.

Conventions enforced here (matching the textbook, Tanenbaum et al. 6th ed.):
  * Line rates use DECIMAL prefixes:  kbps/Mbps/Gbps/Tbps = 10^3/10^6/10^9/10^12 bits/sec.
  * Storage sizes use BINARY prefixes: KB/MB/GB/TB         = 2^10/2^20/2^30/2^40 bytes.

The two systems live in separate code paths so a decimal kilo can never silently
collide with a binary kilo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


# ---------------------------------------------------------------------------
# Metric prefixes (Fig. 1-39). Sub-unit prefixes are lowercase, super-unit
# prefixes are capitalized, EXCEPT the historical `kbps` exception.
# ---------------------------------------------------------------------------
PREFIXES: Dict[str, Tuple[int, str]] = {
    # name -> (exponent, "sub"/"sup")
    "milli": (-3, "sub"),
    "micro": (-6, "sub"),
    "nano": (-9, "sub"),
    "pico": (-12, "sub"),
    "femto": (-15, "sub"),
    "atto": (-18, "sub"),
    "zepto": (-21, "sub"),
    "yocto": (-24, "sub"),
    "kilo": (3, "sup"),
    "mega": (6, "sup"),
    "giga": (9, "sup"),
    "tera": (12, "sup"),
    "peta": (15, "sup"),
    "exa": (18, "sup"),
    "zetta": (21, "sup"),
    "yotta": (24, "sup"),
}

BITS_PER_BYTE = 8

# Decimal line-rate multipliers (powers of ten).
RATE_MULTIPLIER: Dict[str, int] = {
    "bps": 1,
    "kbps": 10 ** 3,
    "Mbps": 10 ** 6,
    "Gbps": 10 ** 9,
    "Tbps": 10 ** 12,
}

# Binary storage multipliers (powers of two). The textbook convention.
SIZE_MULTIPLIER_BYTES: Dict[str, int] = {
    "B": 1,
    "KB": 1 << 10,
    "MB": 1 << 20,
    "GB": 1 << 30,
    "TB": 1 << 40,
}


def bits_to_bytes(bits: int) -> float:
    """Convert a bit count to bytes (float because of the /8)."""
    return bits / BITS_PER_BYTE


def bytes_to_bits(num_bytes: int) -> int:
    """Convert a byte count to bits."""
    return num_bytes * BITS_PER_BYTE


def decimal_rate_bits(value: float, unit: str) -> int:
    """Turn a line-rate spec like (10, 'Mbps') into bits/sec using powers of ten."""
    if unit not in RATE_MULTIPLIER:
        raise ValueError(
            f"unknown rate unit {unit!r}; expected one of {list(RATE_MULTIPLIER)}"
        )
    return int(value * RATE_MULTIPLIER[unit])


def binary_size_bytes(value: float, unit: str) -> int:
    """Turn a storage spec like (4, 'GB') into bytes using powers of two."""
    if unit not in SIZE_MULTIPLIER_BYTES:
        raise ValueError(
            f"unknown size unit {unit!r}; expected one of {list(SIZE_MULTIPLIER_BYTES)}"
        )
    return int(value * SIZE_MULTIPLIER_BYTES[unit])


def transfer_time(size_bytes: int, rate_bps: int) -> Dict[str, float]:
    """Minimum transfer time for `size_bytes` over a `rate_bps` link.

    Returns the raw bit count, the rate, seconds, and minutes so the caller can
    audit every step instead of trusting a single magic number.
    """
    if rate_bps <= 0:
        raise ValueError("rate_bps must be positive")
    total_bits = bytes_to_bits(size_bytes)
    seconds = total_bits / rate_bps
    return {
        "size_bytes": float(size_bytes),
        "total_bits": float(total_bits),
        "rate_bps": float(rate_bps),
        "seconds": seconds,
        "minutes": seconds / 60.0,
    }


# ---------------------------------------------------------------------------
# The hybrid reference model (five layers; OSI Presentation/Session dropped).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Layer:
    number: int
    name: str
    examples: Tuple[str, ...]


HYBRID_MODEL: Tuple[Layer, ...] = (
    Layer(1, "Physical", ("DSL", "SONET", "PSTN", "802.11 PHY", "cable TV")),
    Layer(2, "Link", ("Ethernet", "802.11", "switched Ethernet", "RFID", "DSL framing")),
    Layer(3, "Network", ("IP", "ICMP", "routing algorithms", "congestion control", "QoS")),
    Layer(4, "Transport", ("TCP", "UDP")),
    Layer(5, "Application", ("HTTP", "SMTP", "DNS", "RTP", "FTP", "TELNET")),
)

# Map free-text problem descriptions to a layer. Keywords are deliberately concrete.
LAYER_KEYWORDS: Dict[int, Tuple[str, ...]] = {
    1: ("signal", "modulation", "fiber", "wireless phy", "db", "frequency", "clock", "attenuation"),
    2: (
        "frame", "crc", "mac", "csma", "collision", "backoff", "ethernet",
        "802.11", "switch", "vlan", "arq", "sliding window", "wi-fi",
    ),
    3: (
        "route", "routing", "ip", "icmp", "congestion", "qos", "bgp", "ospf",
        "as-loop", "ttl", "fragment", "subnet",
    ),
    4: (
        "tcp", "udp", "reliab", "flow control", "congestion window",
        "slow start", "ack", "sequence number", "window",
    ),
    5: (
        "http", "dns", "smtp", "email", "web", "rtp", "cdn", "rtt",
        "name resolution", "glue record", "content-type",
    ),
}


def classify_problem(description: str) -> Layer:
    """Return the hybrid-model layer a problem description most likely belongs to."""
    text = description.lower()
    best_layer = 5  # default to application if nothing matches
    best_score = 0
    for number, keywords in LAYER_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_layer = number
    for layer in HYBRID_MODEL:
        if layer.number == best_layer:
            return layer
    raise RuntimeError("no layer matched")  # pragma: no cover - defensive


def print_prefix_table() -> None:
    print("Metric prefixes (Fig. 1-39):")
    print(f"  {'Prefix':<8} {'Exp':<6} {'Decimal':<22} class")
    subs = [(n, e) for n, (e, c) in PREFIXES.items() if c == "sub"]
    sups = [(n, e) for n, (e, c) in PREFIXES.items() if c == "sup"]

    def fmt(exponent: int) -> str:
        # Use fractions for the tiny sub-unit values to dodge float dust; use
        # plain integers for the large super-unit values.
        if exponent < 0:
            num = 10 ** abs(exponent)
            return f"1/{num:,}"
        return f"{10 ** exponent:,}"

    for (n, e) in subs:
        print(f"  {n:<8} {f'10^{e}':<6} {fmt(e):<22} sub-unit (lowercase)")
    for (n, e) in sups:
        print(f"  {n:<8} {f'10^{e}':<6} {fmt(e):<22} super-unit (capitalized)")


def print_model() -> None:
    print("\nHybrid reference model (five layers):")
    for layer in HYBRID_MODEL:
        print(f"  L{layer.number} {layer.name:<12} e.g. {', '.join(layer.examples)}")
    print("  (OSI Presentation L6 and Session L5 dropped -- folded into Application.)")


def demo_backup_window() -> None:
    print("\n--- Worked example: 4-GB snapshot over a 10-Mbps WAN ---")
    size_bytes = binary_size_bytes(4, "GB")
    rate_bps = decimal_rate_bits(10, "Mbps")
    result = transfer_time(size_bytes, rate_bps)
    print(f"  4 GB (binary)      = {int(result['size_bytes']):,} bytes")
    print(f"  10 Mbps (decimal)  = {int(result['rate_bps']):,} bits/sec")
    print(f"  payload in bits    = {int(result['total_bits']):,} bits")
    print(f"  floor time         = {result['seconds']:.2f} s  ({result['minutes']:.2f} min)")
    # The buggy estimate for contrast: the engineer reads "10 Mbps" as "10 MB/s"
    # (byte/bit swap) and "4 GB" as "4 x 10^9 bytes" (binary->decimal swap), then
    # divides bytes by bytes/sec -- so no *8 here, the error is the unit swap itself.
    wrong_seconds = (4 * 10 ** 9) / (10 * 10 ** 6)
    print(f"  naive (wrong) est. = {wrong_seconds:.2f} s  (mixed byte/bit + decimal/binary)")
    print(f"  error factor       = {result['seconds'] / wrong_seconds:.1f}x")


def demo_classify() -> None:
    print("\n--- Classify problems onto the hybrid model ---")
    samples = [
        "two Wi-Fi stations pick the same CSMA/CA backoff slot and collide",
        "a TCP receiver advertises a zero window to throttle the sender",
        "a BGP update creates an AS-level routing loop",
        "an Ethernet frame arrives with a failed CRC and is discarded",
        "a DNS response carries a stale TTL on a glue record",
        "fiber attenuation measured in dB/km limits the link length",
    ]
    for s in samples:
        layer = classify_problem(s)
        print(f"  L{layer.number} {layer.name:<12} <- {s}")


def main() -> None:
    print_prefix_table()
    print_model()
    demo_backup_window()
    demo_classify()


if __name__ == "__main__":
    main()
