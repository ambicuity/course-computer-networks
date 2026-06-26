#!/usr/bin/env python3
"""NAT (Network Address Translation) simulator — RFC 3022 / Tanenbaum §5.6.5.

Demonstrates the full NAT translation mechanism:
  - RFC 1918 private address recognition
  - Outbound packet rewriting: private (IP, port) -> public (IP, ext_port)
  - Inbound demultiplexing: ext_port -> (private IP, private port)
  - IP header checksum recomputation after source-address rewrite
  - Port forwarding (static NAT entries)
  - Capacity calculation: 65,536 − 4,096 = 61,440 max simultaneous flows
  - FTP ALG: embedded IP address rewriting in the application payload

Run:  python3 main.py
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# RFC 1918 private address ranges
# ---------------------------------------------------------------------------

RFC1918_RANGES: list[tuple[str, int]] = [
    ("10.0.0.0",    8),   # 10.0.0.0/8       — 16,777,216 hosts
    ("172.16.0.0", 12),   # 172.16.0.0/12    —  1,048,576 hosts
    ("192.168.0.0", 16),  # 192.168.0.0/16   —     65,536 hosts
]


def ip_to_int(addr: str) -> int:
    """Convert dotted-decimal IPv4 address to 32-bit integer."""
    result = 0
    for octet in addr.split("."):
        result = (result << 8) | int(octet)
    return result


def is_private(addr: str) -> bool:
    """Return True if addr falls in any RFC 1918 private range."""
    ip_int = ip_to_int(addr)
    for network, prefix_len in RFC1918_RANGES:
        mask = ~((1 << (32 - prefix_len)) - 1) & 0xFFFFFFFF
        if (ip_int & mask) == (ip_to_int(network) & mask):
            return True
    return False


# ---------------------------------------------------------------------------
# IP one's-complement checksum (RFC 791 §3.1)
# ---------------------------------------------------------------------------


def ip_checksum(data: bytes) -> int:
    """Compute the RFC 791 one's-complement checksum over *data*."""
    if len(data) % 2:
        data = data + b"\x00"
    total = 0
    for i in range(0, len(data), 2):
        total += (data[i] << 8) | data[i + 1]
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def build_ip_header(src_ip: str, dst_ip: str, proto: int = 6) -> bytes:
    """Build a minimal 20-byte IPv4 header with a valid checksum."""
    ver_ihl = (4 << 4) | 5
    hdr = struct.pack(
        "!BBHHHBBHII",
        ver_ihl, 0, 20, 0x1A2B, 0x4000,  # DF bit set
        64, proto, 0, ip_to_int(src_ip), ip_to_int(dst_ip),
    )
    cksum = ip_checksum(hdr)
    return hdr[:10] + struct.pack("!H", cksum) + hdr[12:]


# ---------------------------------------------------------------------------
# Packet dataclass
# ---------------------------------------------------------------------------


@dataclass
class Packet:
    src_ip:   str
    dst_ip:   str
    src_port: int
    dst_port: int
    protocol: str = "TCP"
    payload:  bytes = field(default=b"")

    def __str__(self) -> str:
        return (f"{self.src_ip}:{self.src_port} -> "
                f"{self.dst_ip}:{self.dst_port} [{self.protocol}]")


# ---------------------------------------------------------------------------
# NAT translation table (RFC 3022 §3)
# ---------------------------------------------------------------------------


@dataclass
class _TableEntry:
    private_ip:   str
    private_port: int


class NATTable:
    """
    Per-connection state maintained by a NAT box.

    The 16-bit port field provides 65,536 slots total.
    Ports 0–4095 are excluded (reserved / well-known services),
    leaving MAX_FLOWS = 61,440 simultaneous flows per public IP.
    """

    FIRST_DYNAMIC_PORT: int = 4096
    MAX_PORT:           int = 65535
    MAX_FLOWS:          int = MAX_PORT - FIRST_DYNAMIC_PORT + 1  # 61,440

    def __init__(self, public_ip: str) -> None:
        self.public_ip = public_ip
        # ext_port -> _TableEntry  (forward lookup: inbound)
        self._table:   dict[int, _TableEntry]          = {}
        # (private_ip, private_port) -> ext_port  (reverse: outbound)
        self._reverse: dict[tuple[str, int], int]      = {}
        self._next_port: int = self.FIRST_DYNAMIC_PORT
        # Static port-forwarding entries ("opening a port")
        self._static:  dict[int, _TableEntry]          = {}

    # ------------------------------------------------------------------ #
    # Internal: port allocation                                            #
    # ------------------------------------------------------------------ #

    def _alloc_port(self) -> int:
        """Return the next free ephemeral port in the NAT pool."""
        start = self._next_port
        while True:
            candidate = self._next_port
            self._next_port = (
                candidate + 1
                if candidate < self.MAX_PORT
                else self.FIRST_DYNAMIC_PORT
            )
            if candidate not in self._table and candidate not in self._static:
                return candidate
            if self._next_port == start:
                raise RuntimeError("NAT table exhausted — no free external ports")

    # ------------------------------------------------------------------ #
    # Outbound: private → public                                           #
    # ------------------------------------------------------------------ #

    def outbound(self, pkt: Packet) -> Packet:
        """
        Rewrite an outbound packet.

        Replaces the private source IP and source port with the public IP
        and a synthetic external port that indexes this table entry.
        A new entry is created if this (private_ip, private_port) pair has
        not been seen before.
        """
        key = (pkt.src_ip, pkt.src_port)
        if key not in self._reverse:
            ext_port = self._alloc_port()
            self._table[ext_port] = _TableEntry(pkt.src_ip, pkt.src_port)
            self._reverse[key] = ext_port
        ext_port = self._reverse[key]
        return Packet(
            src_ip=self.public_ip,
            dst_ip=pkt.dst_ip,
            src_port=ext_port,
            dst_port=pkt.dst_port,
            protocol=pkt.protocol,
            payload=pkt.payload,
        )

    # ------------------------------------------------------------------ #
    # Inbound: public → private                                            #
    # ------------------------------------------------------------------ #

    def inbound(self, pkt: Packet) -> Optional[Packet]:
        """
        Demultiplex an inbound reply packet.

        Looks up pkt.dst_port in the translation table (dynamic or static)
        and rewrites the destination IP and port to the original private values.
        Returns None if no entry exists — the packet is dropped.
        """
        entry = self._table.get(pkt.dst_port) or self._static.get(pkt.dst_port)
        if entry is None:
            return None  # drop — no NAT table entry
        return Packet(
            src_ip=pkt.src_ip,
            dst_ip=entry.private_ip,
            src_port=pkt.src_port,
            dst_port=entry.private_port,
            protocol=pkt.protocol,
            payload=pkt.payload,
        )

    # ------------------------------------------------------------------ #
    # Static port forwarding                                               #
    # ------------------------------------------------------------------ #

    def add_port_forward(
        self, ext_port: int, private_ip: str, private_port: int
    ) -> None:
        """
        Insert a static NAT entry (port forwarding / "opening a port").
        Allows inbound connections without a prior outbound packet.
        """
        self._static[ext_port] = _TableEntry(private_ip, private_port)

    # ------------------------------------------------------------------ #
    # Display                                                              #
    # ------------------------------------------------------------------ #

    def dump(self) -> None:
        print(f"  {'Ext Port':<12} {'Private IP':<18} {'Private Port':<14} Type")
        print("  " + "-" * 60)
        for ext_port, e in sorted(self._table.items()):
            print(f"  {ext_port:<12} {e.private_ip:<18} {e.private_port:<14} dynamic")
        for ext_port, e in sorted(self._static.items()):
            print(f"  {ext_port:<12} {e.private_ip:<18} {e.private_port:<14} static (port-forward)")

    @property
    def active_flows(self) -> int:
        return len(self._table) + len(self._static)


# ---------------------------------------------------------------------------
# FTP ALG: Application Layer Gateway demo
# ---------------------------------------------------------------------------


def ftp_alg_rewrite(
    port_cmd: bytes, public_ip: str, nat: NATTable
) -> tuple[bytes, int]:
    """
    Simulate an FTP ALG rewriting an active-mode PORT command.

    FTP PORT syntax:  PORT a1,a2,a3,a4,p1,p2
    Embedded IP  = a1.a2.a3.a4
    Embedded port = p1 * 256 + p2

    The ALG replaces the private IP with the public IP, allocates a NAT
    entry for the incoming data connection, and updates the port fields.
    Returns (rewritten_command_bytes, allocated_external_port).
    """
    text = port_cmd.decode("ascii")
    keyword, fields_str = text.strip().split(" ", 1)
    fields = fields_str.split(",")
    private_ip = ".".join(fields[:4])
    private_port = int(fields[4]) * 256 + int(fields[5])

    # Allocate a NAT entry so the inbound data connection can be forwarded
    key = (private_ip, private_port)
    if key not in nat._reverse:
        ext_port = nat._alloc_port()
        nat._table[ext_port] = _TableEntry(private_ip, private_port)
        nat._reverse[key] = ext_port
    ext_port = nat._reverse[key]

    pub_octets = public_ip.split(".")
    p1, p2 = ext_port >> 8, ext_port & 0xFF
    new_cmd = (
        f"PORT {pub_octets[0]},{pub_octets[1]},"
        f"{pub_octets[2]},{pub_octets[3]},{p1},{p2}"
    )
    return new_cmd.encode("ascii"), ext_port


# ---------------------------------------------------------------------------
# Demonstration helpers
# ---------------------------------------------------------------------------


def section(title: str) -> None:
    print()
    print("=" * 64)
    print(f"  {title}")
    print("=" * 64)


# ---------------------------------------------------------------------------
# Demo 1: RFC 1918 private address classification
# ---------------------------------------------------------------------------


def demo_rfc1918() -> None:
    section("RFC 1918 Private Address Ranges")
    candidates = [
        ("10.0.0.1",         "10.0.0.0/8"),
        ("10.255.255.255",   "10.0.0.0/8"),
        ("172.16.0.1",       "172.16.0.0/12"),
        ("172.31.255.254",   "172.16.0.0/12"),
        ("192.168.1.100",    "192.168.0.0/16"),
        ("192.168.255.255",  "192.168.0.0/16"),
        ("8.8.8.8",          "public"),
        ("93.184.216.34",    "public"),
        ("198.60.42.12",     "public"),
    ]
    print(f"  {'Address':<22} {'Private?':<8}  Note")
    print("  " + "-" * 55)
    for addr, note in candidates:
        tag = "YES — RFC 1918" if is_private(addr) else "no"
        print(f"  {addr:<22} {tag:<16}  ({note})")


# ---------------------------------------------------------------------------
# Demo 2: Outbound and inbound packet translation
# ---------------------------------------------------------------------------


def demo_translation() -> NATTable:
    section("Outbound Packet Transformation (private → public)")
    PUBLIC_IP = "198.60.42.12"
    nat = NATTable(PUBLIC_IP)

    # Exercise the exact scenario described in the prose:
    # two different hosts using port 5000, one host with two connections
    outbound_packets = [
        Packet("10.0.0.1", "93.184.216.34", 5544, 80,  "TCP"),
        Packet("10.0.0.2", "93.184.216.34", 5000, 80,  "TCP"),   # different host, same port
        Packet("10.0.0.1", "93.184.216.34", 5000, 443, "TCP"),   # same host, second conn
        Packet("10.0.0.3", "8.8.8.8",       5001, 53,  "UDP"),
    ]

    for pkt in outbound_packets:
        translated = nat.outbound(pkt)
        print(f"  BEFORE: {pkt}")
        print(f"  AFTER:  {translated}")
        print()

    section("NAT Translation Table (state after outbound packets)")
    nat.dump()
    print(f"\n  Active flows: {nat.active_flows}")

    section("Inbound Demultiplexing (server replies → private hosts)")
    # ext_port 4096 was allocated to 10.0.0.1:5544 (first packet)
    test_ports = [4096, 4097, 4098, 4099, 9999]
    for ext_port in test_ports:
        reply = Packet("93.184.216.34", PUBLIC_IP, 80, ext_port, "TCP")
        result = nat.inbound(reply)
        if result:
            print(f"  dst_port={ext_port} -> {result.dst_ip}:{result.dst_port} [FORWARDED]")
        else:
            print(f"  dst_port={ext_port} -> (no entry — packet DROPPED)")

    return nat


# ---------------------------------------------------------------------------
# Demo 3: Port forwarding (static NAT)
# ---------------------------------------------------------------------------


def demo_port_forwarding(nat: NATTable) -> None:
    section("Port Forwarding — Static NAT Entry ('opening a port')")
    nat.add_port_forward(80, "10.0.0.10", 8080)
    print("  Static entry added: public:80 -> 10.0.0.10:8080")
    print()
    req = Packet("5.6.7.8", nat.public_ip, 43210, 80, "TCP")
    result = nat.inbound(req)
    print(f"  Inbound packet: {req}")
    if result:
        print(f"  Forwarded to:   {result.dst_ip}:{result.dst_port}")

    # Confirm an unregistered port is still dropped
    unsolicited = Packet("5.6.7.8", nat.public_ip, 43210, 22, "TCP")
    blocked = nat.inbound(unsolicited)
    print()
    print(f"  Unsolicited inbound (port 22): {unsolicited}")
    print(f"  Result: {'DROPPED — no table entry' if blocked is None else blocked}")


# ---------------------------------------------------------------------------
# Demo 4: Checksum recomputation after field rewrites
# ---------------------------------------------------------------------------


def demo_checksum() -> None:
    section("IP Header Checksum Recomputation After NAT Rewrite")
    private_src = "10.0.0.1"
    public_src  = "198.60.42.12"
    dst         = "93.184.216.34"

    hdr_before = build_ip_header(private_src, dst)
    cksum_before = struct.unpack("!H", hdr_before[10:12])[0]

    # NAT rewrites source IP (bytes 12–15) and zeroes checksum field
    hdr_new = (
        hdr_before[:10]
        + b"\x00\x00"
        + hdr_before[12:16]
        + struct.pack("!I", ip_to_int(public_src))
        + hdr_before[20:]
    )
    # Wait — bytes 12-15 are src IP in the IP header layout:
    # bytes 0: ver+ihl, 1: tos, 2-3: total_len, 4-5: ident,
    # 6-7: flags+frag, 8: ttl, 9: proto, 10-11: checksum,
    # 12-15: src IP, 16-19: dst IP
    hdr_rewritten = (
        hdr_before[:10]
        + b"\x00\x00"                              # checksum zeroed
        + struct.pack("!I", ip_to_int(public_src)) # new src IP
        + hdr_before[16:]                          # dst IP unchanged
    )
    new_cksum = ip_checksum(hdr_rewritten)
    hdr_after = hdr_rewritten[:10] + struct.pack("!H", new_cksum) + hdr_rewritten[12:]

    valid_before = ip_checksum(hdr_before) == 0
    valid_after  = ip_checksum(hdr_after)  == 0

    print(f"  Before rewrite:")
    print(f"    src IP = {private_src:<18}  IP checksum = 0x{cksum_before:04X}"
          f"  valid={valid_before}")
    print(f"  After rewrite:")
    print(f"    src IP = {public_src:<18}  IP checksum = 0x{new_cksum:04X}"
          f"  valid={valid_after}")
    print()
    print("  Fields that MUST be updated on outbound NAT rewrite:")
    print("    IP header : source address (bytes 12–15)")
    print("                IP header checksum (bytes 10–11)")
    print("    TCP header: source port (bytes 0–1 of TCP segment)")
    print("                TCP checksum (covers pseudo-header including src IP + src port)")
    assert valid_before and valid_after, "Checksum validation failed"


# ---------------------------------------------------------------------------
# Demo 5: Capacity calculation
# ---------------------------------------------------------------------------


def demo_capacity() -> None:
    section("NAT Capacity Calculation")
    total_ports = 65536          # 2^16
    reserved    = 4096           # ports 0-4095
    max_flows   = total_ports - reserved   # 61,440

    print(f"  2^16 total port slots          : {total_ports:>7,}")
    print(f"  Minus ports 0–4095 (reserved)  : {reserved:>7,}")
    print(f"  Max simultaneous flows (1 IP)  : {max_flows:>7,}")
    print()
    print(f"  NATTable.MAX_FLOWS             : {NATTable.MAX_FLOWS:>7,}")
    assert NATTable.MAX_FLOWS == max_flows, "Capacity constant mismatch"
    print()
    print("  With N public IPs: capacity = N × 61,440 simultaneous flows")
    for n in (1, 2, 4, 8):
        print(f"    {n} public IP(s): {n * max_flows:>10,} simultaneous flows")


# ---------------------------------------------------------------------------
# Demo 6: FTP ALG
# ---------------------------------------------------------------------------


def demo_alg() -> None:
    section("FTP ALG — Application Layer Gateway (Fixing Objection #6)")
    PUBLIC_IP  = "198.60.42.12"
    PRIVATE_IP = "10.0.0.5"
    nat = NATTable(PUBLIC_IP)

    # FTP active-mode PORT command with embedded private IP
    # PORT 10,0,0,5,20,5  =>  IP=10.0.0.5, data port=20*256+5=5125
    original_cmd = b"PORT 10,0,0,5,20,5"
    print(f"  Original FTP PORT command : {original_cmd.decode()}")
    print(f"    Embedded address = {PRIVATE_IP}, data port = 5125")
    print()
    print("  Without ALG: FTP server tries to connect to 10.0.0.5 —")
    print("    a private address unreachable from the Internet.")
    print("    The data transfer fails silently.")
    print()

    rewritten, ext_port = ftp_alg_rewrite(original_cmd, PUBLIC_IP, nat)
    print(f"  After ALG rewrite : {rewritten.decode()}")
    print(f"    NAT ext_port allocated for data connection: {ext_port}")
    print()
    # Verify the inbound data connection can be demultiplexed
    inbound_data = Packet("93.184.216.34", PUBLIC_IP, 20, ext_port, "TCP")
    result = nat.inbound(inbound_data)
    print(f"  Server opens data conn to public:{ext_port}")
    if result:
        print(f"    NAT forwards to: {result.dst_ip}:{result.dst_port} [OK]")


# ---------------------------------------------------------------------------
# Demo 7: Architectural objections summary
# ---------------------------------------------------------------------------


def demo_objections() -> None:
    section("NAT Architectural Objections (RFC 2993)")
    objections = [
        (
            1, "Unique address model",
            "RFC 791 states every IP address identifies exactly one machine.\n"
            "    NAT allows up to 61,440 private hosts to share one public IP.",
        ),
        (
            2, "End-to-end connectivity",
            "The mapping is created by outbound packets only.\n"
            "    A remote host cannot initiate a connection without port forwarding.\n"
            "    Peer-to-peer, game servers, and VoIP calling fail by default.",
        ),
        (
            3, "Stateful network",
            "The NAT box must maintain per-connection state.\n"
            "    A NAT crash destroys every active TCP connection — like\n"
            "    circuit-switch failure, not a stateless IP router failure.",
        ),
        (
            4, "Protocol layering",
            "NAT modifies Layer-4 (TCP/UDP) ports while acting as a\n"
            "    Layer-3 (network) device, violating strict layer separation.\n"
            "    If TCP is redesigned with 32-bit ports, all NAT boxes break.",
        ),
        (
            5, "Transport protocol dependence",
            "NAT works only for TCP and UDP. Protocols such as SCTP or\n"
            "    custom transports require explicit NAT support to traverse.",
        ),
        (
            6, "Application payload blindness",
            "NAT only rewrites IP headers and TCP/UDP ports.\n"
            "    Protocols that embed addresses in payloads (FTP, SIP, H.323)\n"
            "    require protocol-specific ALGs — a perpetual arms race.",
        ),
    ]
    for num, name, detail in objections:
        print(f"  {num}. {name}")
        print(f"     {detail}")
        print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 64)
    print("  Network Address Translation (NAT) Simulator")
    print("  RFC 3022 · RFC 1918 · RFC 2993 · Tanenbaum §5.6.5")
    print("=" * 64)

    demo_rfc1918()
    nat = demo_translation()
    demo_port_forwarding(nat)
    demo_checksum()
    demo_capacity()
    demo_alg()
    demo_objections()

    print()
    print("=" * 64)
    print("  All NAT demonstrations completed successfully.")
    print("=" * 64)


if __name__ == "__main__":
    main()
