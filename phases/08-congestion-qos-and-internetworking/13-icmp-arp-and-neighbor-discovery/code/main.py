"""ICMP, ARP, and Neighbor Discovery — stdlib-only encoder/parser and demos.

Demonstrates: 28-byte ARP request/reply (RFC 826), ICMP Echo with the
RFC 1071 Internet checksum, ICMPv6 NS/NA + the solicited-node multicast
address ff02::1:ffXX:XXXX (RFC 4861), an ARP cache with timeout, and a
traceroute simulator that emits TimeExceeded for TTL=1, 2, 3, ...
Run: python3 main.py   Exit: 0. No pip deps.
"""
from __future__ import annotations
import struct, time
from dataclasses import dataclass, field

# --- ARP --------------------------------------------------------------------
ARP_HTYPE_ETHERNET, ARP_PTYPE_IPV4 = 1, 0x0800
ARP_HLEN, ARP_PLEN = 6, 4
ARP_REQUEST, ARP_REPLY = 1, 2
ETHER_TYPE_ARP = 0x0806
BROADCAST_MAC = b"\xff\xff\xff\xff\xff\xff"
ARP_CACHE_TIMEOUT_S = 20 * 60
ICMP_ECHO_REQUEST, ICMP_ECHO_REPLY = 8, 0
ICMPV6_NS, ICMPV6_NA = 135, 136


def encode_arp(opcode, smac, sip, tmac, tip):
    if len(smac) != 6 or len(tmac) != 6 or len(sip) != 4 or len(tip) != 4:
        raise ValueError("bad MAC or IPv4 size")
    return struct.pack("!HHBBH6s4s6s4s", ARP_HTYPE_ETHERNET, ARP_PTYPE_IPV4,
                       ARP_HLEN, ARP_PLEN, opcode, smac, sip, tmac, tip)


@dataclass
class ArpPacket:
    htype: int; ptype: int; hlen: int; plen: int; opcode: int
    sender_mac: bytes; sender_ip: bytes; target_mac: bytes; target_ip: bytes


def parse_arp(buf):
    if len(buf) < 28:
        raise ValueError("ARP message must be >= 28 bytes")
    h, p, hl, pl, op, sm, si, tm, ti = struct.unpack("!HHBBH6s4s6s4s", buf[:28])
    return ArpPacket(h, p, hl, pl, op, sm, si, tm, ti)


@dataclass
class ArpCache:
    timeout_s: int = ARP_CACHE_TIMEOUT_S
    entries: dict[str, tuple[bytes, float]] = field(default_factory=dict)

    def put(self, ip, mac):
        self.entries[ip.hex()] = (mac, time.monotonic() + self.timeout_s)

    def get(self, ip):
        entry = self.entries.get(ip.hex())
        if entry is None:
            return None
        mac, exp = entry
        if time.monotonic() > exp:
            del self.entries[ip.hex()]
            return None
        return mac

    def purge_expired(self):
        now = time.monotonic()
        keys = [k for k, (_, e) in self.entries.items() if now > e]
        for k in keys: del self.entries[k]
        return len(keys)


# --- ICMPv4 (Echo + Internet checksum) --------------------------------------
def internet_checksum(data):
    """RFC 1071 16-bit one's complement of the one's complement 16-bit sum."""
    if len(data) % 2: data = data + b"\x00"
    total = sum((data[i] << 8) | data[i + 1] for i in range(0, len(data), 2))
    while total >> 16: total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def encode_icmp_echo(icmp_type, ident, seq, payload):
    hdr0 = struct.pack("!BBHHH", icmp_type, 0, 0, ident, seq)
    cksum = internet_checksum(hdr0 + payload)
    return struct.pack("!BBHHH", icmp_type, 0, cksum, ident, seq) + payload


def verify_icmp_checksum(msg):
    """Recompute on a received message. Correct => folded sum == 0xFFFF."""
    data = msg + b"\x00" if len(msg) % 2 else msg
    total = sum((data[i] << 8) | data[i + 1] for i in range(0, len(data), 2))
    while total >> 16: total = (total & 0xFFFF) + (total >> 16)
    return (total & 0xFFFF) == 0xFFFF


# --- ICMPv6 / NDP -----------------------------------------------------------
def ipv6_str(addr): return ":".join(f"{g:04x}" for g in struct.unpack("!8H", addr))


def ipv6_from_str(s):
    parts = s.split(":")
    if len(parts) != 8 or any(p == "" for p in parts):
        raise ValueError(f"expected 8 colon-separated 16-bit groups, got {s!r}")
    return struct.pack("!8H", *(int(p, 16) for p in parts))


def solicited_node_mcast(target):
    """ff02::1:ff{T23:T16}:{T15:T0} — last 24 bits of target in low 24 of last 2 groups."""
    return struct.pack("!8H", 0xFF02, 0, 0, 0, 0, 0x0001,
                       0xFF00 | target[13], (target[14] << 8) | target[15])


def encode_icmpv6_ns(target):
    return struct.pack("!BBH", ICMPV6_NS, 0, 0) + b"\x00" * 4 + target


def encode_icmpv6_na(target, r=True, s=True, o=True):
    flags = ((1 << 7) if r else 0) | ((1 << 6) if s else 0) | ((1 << 5) if o else 0)
    return struct.pack("!BBHI", ICMPV6_NA, 0, flags, 0) + target


# --- traceroute simulator ---------------------------------------------------
@dataclass
class Hop:
    addr: str
    delay_ms: int


def traceroute(route, probes_per_hop=3):
    trace = []
    for ttl, hop in enumerate(route, start=1):
        kind = "ICMP TimeExceeded" if ttl < len(route) else "ICMP EchoReply / PortUnreach"
        for probe in range(probes_per_hop):
            trace.append({"ttl": ttl, "probe": probe + 1, "from": hop.addr,
                          "rtt_ms": hop.delay_ms + probe, "kind": kind})
    return trace


# --- helpers ----------------------------------------------------------------
mac_str = lambda m: ":".join(f"{b:02x}" for b in m)  # noqa: E731
ip_str = lambda i: ".".join(str(b) for b in i)       # noqa: E731


# --- demonstrations ---------------------------------------------------------
def main():
    print("ICMP, ARP, and Neighbor Discovery — packet demonstrations\n")
    HR, HL = "=" * 72, "-" * 50

    # [1] ARP roundtrip
    print(HR, "[1] ARP request/reply — 28-byte wire format", HR, sep="\n")
    smac, sip = bytes.fromhex("aabbcc112233"), bytes([10, 0, 0, 42])
    tmac, tip = bytes(6), bytes([10, 0, 0, 7])
    req, p = encode_arp(ARP_REQUEST, smac, sip, tmac, tip), None
    p = parse_arp(req)
    print(f"  Ethernet dst (request): {mac_str(BROADCAST_MAC)}  EtherType: 0x{ETHER_TYPE_ARP:04x}")
    print(f"  ARP request hex  ({len(req)}B): {req.hex()}")
    print(f"  parsed: opcode={p.opcode} htype={p.htype} ptype=0x{p.ptype:04x} hlen={p.hlen} plen={p.plen}")
    print(f"          sender IP={ip_str(p.sender_ip)} sender MAC={mac_str(p.sender_mac)}")
    print(f"          target IP={ip_str(p.target_ip)} target MAC={mac_str(p.target_mac)}")
    rmac = bytes.fromhex("ddeeff445566")
    reply, pr = encode_arp(ARP_REPLY, rmac, tip, smac, sip), parse_arp(encode_arp(ARP_REPLY, rmac, tip, smac, sip))
    print(f"  Ethernet dst (reply):   {mac_str(smac)}  (unicast)")
    print(f"  parsed reply: opcode={pr.opcode} sender MAC={mac_str(pr.sender_mac)}\n")

    # [2] ICMP Echo + Internet checksum
    print(HR, "[2] ICMP Echo Request / Reply — Internet checksum", HR, sep="\n")
    payload = b"ping-the-network!"
    req = encode_icmp_echo(ICMP_ECHO_REQUEST, 0xBEEF, 1, payload)
    print(f"  Echo Request  ({len(req)}B): {req.hex()}")
    print(f"    type={req[0]} code={req[1]} checksum=0x{struct.unpack('!H', req[2:4])[0]:04x} "
          f"id=0x{struct.unpack('!H', req[4:6])[0]:04x} seq={struct.unpack('!H', req[6:8])[0]}")
    assert verify_icmp_checksum(req), "Echo Request checksum failed"
    rep = encode_icmp_echo(ICMP_ECHO_REPLY, 0xBEEF, 1, payload)
    print(f"  Echo Reply    ({len(rep)}B): {rep.hex()}")
    print(f"    type={rep[0]} checksum=0x{struct.unpack('!H', rep[2:4])[0]:04x}  (verified)")
    assert verify_icmp_checksum(rep), "Echo Reply checksum failed"
    print("  -> both packets pass; flip one bit and verify_icmp_checksum returns False.\n")

    # [3] ICMPv6 NDP + solicited-node
    print(HR, "[3] ICMPv6 NDP — Neighbor Solicitation + solicited-node multicast", HR, sep="\n")
    target = ipv6_from_str("2001:0db8:0000:0000:0000:0000:abcd:1234")
    snm, ns, na = solicited_node_mcast(target), encode_icmpv6_ns(target), encode_icmpv6_na(target)
    flags = struct.unpack("!H", na[2:4])[0]
    print(f"  target IPv6          : {ipv6_str(target)}")
    print(f"  solicited-node mcast : {ipv6_str(snm)}  (last 24 bits copied)")
    print(f"  NS ({len(ns)}B): type={ns[0]} target={ipv6_str(ns[8:24])}")
    print(f"  NA ({len(na)}B): type={na[0]} flags=0x{flags:04x} "
          f"R={(flags >> 7) & 1} S={(flags >> 6) & 1} O={(flags >> 5) & 1} "
          f"target={ipv6_str(na[8:24])}")
    print("  state machine: INCOMPLETE -> REACHABLE -> STALE -> DELAY -> PROBE")
    print("                  (REACHABLE_TIME=30s, DELAY_FIRST_PROBE_TIME=5s)\n")

    # [4] Traceroute
    print(HR, "[4] Traceroute simulator — TTL=1, 2, 3, ... TimeExceeded", HR, sep="\n")
    route = [Hop("10.0.0.1", 1), Hop("192.0.2.1", 8),
             Hop("203.0.113.1", 22), Hop("198.51.100.42", 35)]
    print(f"  {'ttl':>3}  {'probe':>5}  {'from':<16}  {'rtt_ms':>6}  response")
    for e in traceroute(route):
        print(f"  {e['ttl']:>3}  {e['probe']:>5}  {e['from']:<16}  {e['rtt_ms']:>6}  {e['kind']}")
    print()

    # [5] ARP cache
    print(HR, "[5] ARP cache — lookup with 20-min timeout", HR, sep="\n")
    cache, ip, mac = ArpCache(), bytes([10, 0, 0, 7]), bytes.fromhex("ddeeff445566")
    cache.put(ip, mac)
    got = cache.get(ip)
    print(f"  put({ip_str(ip)}) -> {mac_str(mac)}  (expires in {cache.timeout_s}s)")
    print(f"  get({ip_str(ip)}) -> {mac_str(got) if got else 'None'}")
    print(f"  ARP cache: {len(cache.entries)} live entries, "
          f"{cache.purge_expired()} expired (none in a fresh cache).\n")

    print("All demos completed. Exit 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
