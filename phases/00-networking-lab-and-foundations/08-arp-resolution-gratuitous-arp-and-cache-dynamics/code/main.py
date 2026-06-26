"""ARP resolution, gratuitous ARP, and cache dynamics.

A stdlib-only model of the IPv4 Address Resolution Protocol (RFC 826) plus the
gratuitous-ARP behaviours documented in RFC 5227 and the cache-lifetime rules
used by Linux/Windows/macOS (REACHABLE -> STALE -> garbage-collected).

It builds ARP Ethernet frames (28-byte ARP payload + 14-byte Ether header),
walks a small LAN through request/reply, gratuitous-ARP, proxy-ARP, and a
cache that ages out by a hard timeout, and prints the resulting cache state.

No network calls, no third-party packages.  Run with:

    python3 main.py
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants (from RFC 826 and the IEEE 802.3 EtherType registry)
# ---------------------------------------------------------------------------

HTYPE_ETHERNET = 1          # Hardware type: Ethernet
PTYPE_IPV4 = 0x0800         # Protocol type: IPv4
HLEN_ETHER = 6              # MAC address length in bytes
PLEN_IPV4 = 4               # IPv4 address length in bytes
ETHER_HDR_LEN = 14          # dst(6) + src(6) + ethertype(2)
ARP_PAYLOAD_LEN = 28        # htype/ptype/hlen/plen/op(8) + sha(6)+spa(4)+tha(6)+tpa(4)
BCAST_MAC = "ff:ff:ff:ff:ff:ff"
ZERO_MAC = "00:00:00:00:00:00"
ETH_TYPE_ARP = 0x0806

# Common default cache timeouts (seconds). Real kernels vary widely; these
# approximate the Linux "reachable" (DELAY->STALE transition) and gc_stale_time.
DEFAULT_BASE_REACHABLE_MS = 30000   # 30s before REACHABLE -> STALE
DEFAULT_GC_TIMEOUT_S = 60           # gc_stale_time on Linux for stale entries


class ArpOp(IntEnum):
    REQUEST = 1
    REPLY = 2
    RARP_REQUEST = 3
    RARP_REPLY = 4


# ---------------------------------------------------------------------------
# Address helpers
# ---------------------------------------------------------------------------

def ip_to_int(ip: str) -> int:
    """Convert dotted-quad IPv4 string to a 32-bit integer."""
    parts = ip.split(".")
    if len(parts) != 4:
        raise ValueError(f"bad IPv4: {ip!r}")
    n = 0
    for p in parts:
        b = int(p)
        if not 0 <= b <= 255:
            raise ValueError(f"octet out of range: {p!r}")
        n = (n << 8) | b
    return n


def int_to_ip(n: int) -> str:
    return ".".join(str((n >> (8 * i)) & 0xFF) for i in (3, 2, 1, 0))


def mac_to_bytes(mac: str) -> bytes:
    b = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    if len(b) != 6:
        raise ValueError(f"bad MAC: {mac!r}")
    return b


def bytes_to_mac(b: bytes) -> str:
    return ":".join(f"{x:02x}" for x in b)


# ---------------------------------------------------------------------------
# ARP packet (RFC 826) on top of an Ethernet header
# ---------------------------------------------------------------------------

@dataclass
class ArpPacket:
    op: int                  # ArpOp value
    sender_ha: str           # sender hardware (MAC) address
    sender_pa: str           # sender protocol (IPv4) address
    target_ha: str           # target hardware address
    target_pa: str           # target protocol (IPv4) address

    def to_bytes(self) -> bytes:
        return struct.pack(
            "!HHBBH",
            HTYPE_ETHERNET,
            PTYPE_IPV4,
            HLEN_ETHER,
            PLEN_IPV4,
            int(self.op),
        ) + mac_to_bytes(self.sender_ha) + struct.pack("!I", ip_to_int(self.sender_pa)) \
          + mac_to_bytes(self.target_ha) + struct.pack("!I", ip_to_int(self.target_pa))

    @classmethod
    def from_bytes(cls, raw: bytes) -> "ArpPacket":
        if len(raw) < ARP_PAYLOAD_LEN:
            raise ValueError("ARP payload too short")
        _, _, _, _, op = struct.unpack("!HHBBH", raw[:8])
        off = 8
        sha = bytes_to_mac(raw[off:off + 6]); off += 6
        spa = int_to_ip(struct.unpack("!I", raw[off:off + 4])[0]); off += 4
        tha = bytes_to_mac(raw[off:off + 6]); off += 6
        tpa = int_to_ip(struct.unpack("!I", raw[off:off + 4])[0])
        return cls(op, sha, spa, tha, tpa)

    def frame(self, dst_mac: str, src_mac: str) -> bytes:
        """Wrap in an Ethernet header and return a wire frame."""
        eth = mac_to_bytes(dst_mac) + mac_to_bytes(src_mac) + struct.pack("!H", ETH_TYPE_ARP)
        return eth + self.to_bytes()

    def is_gratuitous(self) -> bool:
        """RFC 5227: spa == tpa, broadcast as a REQUEST or unicast as a REPLY."""
        return self.sender_pa == self.target_pa


# ---------------------------------------------------------------------------
# ARP cache with the REACHABLE -> STALE -> gc lifecycle
# ---------------------------------------------------------------------------

@dataclass
class CacheEntry:
    ip: str
    mac: str
    state: str = "REACHABLE"          # REACHABLE -> STALE -> (deleted)
    last_seen: float = field(default_factory=time.monotonic)
    is_static: bool = False

    def age(self, now: float, reachable_s: float, gc_s: float) -> Optional[str]:
        """Return new state, or None if the entry should be garbage collected."""
        if self.is_static:
            return "REACHABLE"
        elapsed = now - self.last_seen
        if elapsed > gc_s:
            return None               # GC
        if elapsed > reachable_s:
            return "STALE"
        return "REACHABLE"


@dataclass
class ArpCache:
    reachable_s: float = DEFAULT_BASE_REACHABLE_MS / 1000.0
    gc_s: float = DEFAULT_GC_TIMEOUT_S
    entries: Dict[str, CacheEntry] = field(default_factory=dict)
    queued: Dict[str, int] = field(default_factory=dict)  # ip -> packets held

    def insert(self, ip: str, mac: str, static: bool = False) -> bool:
        """RFC 826 update rule. Return True if a new/changed entry was installed."""
        e = self.entries.get(ip)
        if e is None:
            self.entries[ip] = CacheEntry(ip, mac, is_static=static)
            return True
        if e.mac != mac:
            e.mac = mac
            e.state = "REACHABLE"
            e.last_seen = time.monotonic()
            return True
        e.last_seen = time.monotonic()
        e.state = "REACHABLE"
        return False

    def lookup(self, ip: str) -> Optional[CacheEntry]:
        return self.entries.get(ip)

    def tick(self, now: float) -> Tuple[int, int]:
        """Age every entry; return (#stale_transitions, #gc'd)."""
        stale = gc = 0
        for ip in list(self.entries):
            new = self.entries[ip].age(now, self.reachable_s, self.gc_s)
            if new is None:
                del self.entries[ip]
                gc += 1
            elif new != self.entries[ip].state:
                self.entries[ip].state = new
                if new == "STALE":
                    stale += 1
        return stale, gc

    def flush(self, ip: str) -> bool:
        return self.entries.pop(ip, None) is not None

    def table(self) -> str:
        lines = ["  IP            MAC                STATE     STATIC"]
        for ip in sorted(self.entries, key=ip_to_int):
            e = self.entries[ip]
            lines.append(f"  {ip:<13} {e.mac:<18} {e.state:<8} {e.is_static}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# A tiny LAN that actually resolves addresses
# ---------------------------------------------------------------------------

@dataclass
class Host:
    name: str
    ip: str
    mac: str
    cache: ArpCache = field(default_factory=ArpCache)

    def resolve(self, target_ip: str, lan: dict) -> Tuple[Optional[str], list]:
        """Resolve target_ip -> mac. Return (mac, trace). Implements RFC 826.

        1. cache hit and REACHABLE -> return immediately
        2. cache hit but STALE -> re-probe (modeled as immediate refresh)
        3. miss -> broadcast REQUEST, queue packet, await REPLY
        """
        trace: list = []
        e = self.cache.lookup(target_ip)
        if e and e.state == "REACHABLE":
            trace.append(f"[{self.name}] cache HIT  {target_ip} -> {e.mac}")
            return e.mac, trace
        if e and e.state == "STALE":
            trace.append(f"[{self.name}] cache STALE -> re-probing {target_ip}")
        else:
            trace.append(f"[{self.name}] cache MISS for {target_ip}; broadcasting REQUEST")

        self.cache.queued.setdefault(target_ip, 0)
        self.cache.queued[target_ip] += 1

        req = ArpPacket(ArpOp.REQUEST, self.mac, self.ip, ZERO_MAC, target_ip)
        frame = req.frame(BCAST_MAC, self.mac)
        trace.append(f"          -> Ether dst={BCAST_MAC} src={self.mac} type=0x0806")
        trace.append(f"          -> ARP op=REQUEST sha={self.mac} spa={self.ip} tpa={target_ip}")

        rep = lan_broadcast(lan, self, frame, target_ip, trace)
        if rep is not None:
            self.cache.insert(rep.sender_pa, rep.sender_ha)
            self.cache.queued.pop(target_ip, None)
            trace.append(f"[{self.name}] got REPLY {target_ip} -> {rep.sender_ha}; cache updated")
            return rep.sender_ha, trace
        trace.append(f"[{self.name}] RESOLUTION FAILED for {target_ip}")
        return None, trace

    def receive_arp(self, pkt: ArpPacket, lan: dict, trace: list) -> Optional[ArpPacket]:
        """RFC 826 receiver: always learn sender; reply if REQUEST targets my IP."""
        # (1) Always cache the sender binding (this is also what makes gratuitous ARP work)
        if pkt.sender_pa != "0.0.0.0":
            changed = self.cache.insert(pkt.sender_pa, pkt.sender_ha)
            tag = "UPDATED" if changed else "refreshed"
            trace.append(f"[{self.name}] learned {pkt.sender_pa} -> {pkt.sender_ha} ({tag})")
        # (2) If a REQUEST targets my IP, reply with my MAC
        if pkt.op == ArpOp.REQUEST and pkt.target_pa == self.ip:
            return ArpPacket(ArpOp.REPLY, self.mac, self.ip, pkt.sender_ha, pkt.sender_pa)
        return None


def lan_broadcast(lan: dict, sender: Host, frame: bytes, wanted_ip: str,
                  trace: list) -> Optional[ArpPacket]:
    """Deliver a broadcast frame to every host except the sender."""
    pkt = ArpPacket.from_bytes(frame[ETHER_HDR_LEN:])
    for host in lan.values():
        if host is sender:
            continue
        rep = host.receive_arp(pkt, lan, trace)
        if rep is not None and pkt.target_pa == host.ip:
            trace.append(f"[{host.name}] answers: op=REPLY sha={host.mac} spa={host.ip} "
                         f"tha={pkt.sender_ha} tpa={pkt.sender_pa}")
            return rep
    return None


# ---------------------------------------------------------------------------
# Top-level scenarios
# ---------------------------------------------------------------------------

def scenario_resolution() -> None:
    print("=" * 72)
    print("Scenario 1: ARP request/reply resolution (RFC 826)")
    print("=" * 72)
    lan = {
        "A": Host("A", "10.0.0.7", "aa:bb:cc:00:00:07"),
        "B": Host("B", "10.0.0.9", "aa:bb:cc:00:00:09"),
        "S": Host("S", "10.0.0.1", "aa:bb:cc:00:00:01"),
    }
    mac, trace = lan["A"].resolve("10.0.0.9", lan)
    print("\n".join(trace))
    print(f"\nResult: 10.0.0.9 resolved to {mac}")
    print("\nA's cache after resolution:")
    print(lan["A"].cache.table())
    print("\nWire bytes of the reply frame (hex):")
    rep = ArpPacket(ArpOp.REPLY, lan["B"].mac, "10.0.0.9", lan["A"].mac, "10.0.0.7")
    print(rep.frame(lan["A"].mac, lan["B"].mac).hex())


def scenario_gratuitous() -> None:
    print("\n" + "=" * 72)
    print("Scenario 2: Gratuitous ARP on a MAC swap (RFC 5227)")
    print("=" * 72)
    lan = {"A": Host("A", "10.0.0.7", "aa:bb:cc:00:00:07"),
           "B": Host("B", "10.0.0.9", "aa:bb:cc:00:00:09")}
    # First B resolves A so B's cache holds the old A MAC.
    lan["B"].resolve("10.0.0.7", lan)
    print("B's cache before gratuitous ARP:")
    print(lan["B"].cache.table())
    # A swaps its NIC and announces itself.
    new_mac = "aa:bb:cc:00:00:77"
    lan["A"].mac = new_mac
    garp = ArpPacket(ArpOp.REQUEST, new_mac, "10.0.0.7", ZERO_MAC, "10.0.0.7")
    print("\nA sends gratuitous ARP (spa == tpa == 10.0.0.7):")
    print(f"  op={ArpOp(garp.op).name} sha={garp.sender_ha} spa={garp.sender_pa} "
          f"tpa={garp.target_pa}  is_gratuitous={garp.is_gratuitous()}")
    trace: list = []
    for h in lan.values():
        if h is lan["A"]:
            continue
        h.receive_arp(garp, lan, trace)
    print("\n".join(trace))
    print("\nB's cache after gratuitous ARP (MAC updated, no query needed):")
    print(lan["B"].cache.table())


def scenario_proxy_arp() -> None:
    print("\n" + "=" * 72)
    print("Scenario 3: Proxy ARP (router answers for an off-LAN host)")
    print("=" * 72)
    proxy_target = "10.0.0.50"
    real_mac = "11:22:33:44:55:66"   # the off-LAN host's real MAC, hidden by the router

    @dataclass
    class Router(Host):
        proxy: Dict[str, str] = field(default_factory=dict)

    a = Host("A", "10.0.0.7", "aa:bb:cc:00:00:07")
    r = Router("R", "10.0.0.1", "aa:bb:cc:00:00:01")
    r.proxy = {proxy_target: real_mac}
    lan = {"A": a, "R": r}

    trace: list = []
    req = ArpPacket(ArpOp.REQUEST, a.mac, "10.0.0.7", ZERO_MAC, proxy_target)
    frame = req.frame(BCAST_MAC, a.mac)
    pkt = ArpPacket.from_bytes(frame[ETHER_HDR_LEN:])
    # R intercepts: its IP is not 10.0.0.50, but it holds a proxy entry for it.
    r.receive_arp(pkt, lan, trace)
    if proxy_target in r.proxy:
        rep = ArpPacket(ArpOp.REPLY, r.mac, proxy_target, a.mac, "10.0.0.7")
        a.cache.insert(proxy_target, r.mac)
        trace.append(f"[R] PROXY-ARP: answered for {proxy_target} with R's own MAC {r.mac}")
        trace.append(f"    (off-LAN host's real MAC {real_mac} is never revealed to A)")
    print("\n".join(trace))
    print("\nA's cache (note the proxy MAC is R's MAC, not the real host's):")
    print(a.cache.table())


def scenario_cache_aging() -> None:
    print("\n" + "=" * 72)
    print("Scenario 4: Cache aging (REACHABLE -> STALE -> GC)")
    print("=" * 72)
    cache = ArpCache(reachable_s=0.4, gc_s=1.2)
    cache.insert("10.0.0.9", "aa:bb:cc:00:00:09")
    t0 = time.monotonic()
    print("t=0.0s fresh insert:")
    print(cache.table())

    time.sleep(0.5)
    s, g = cache.tick(t0 + 0.5)
    print(f"\nt=0.5s after tick: stale_transitions={s} gc={g}")
    print(cache.table())

    time.sleep(1.0)
    s, g = cache.tick(t0 + 1.5)
    print(f"\nt=1.5s after tick: stale_transitions={s} gc={g}  (entry removed)")
    print(cache.table() if cache.entries else "  (empty)")


def scenario_frame_decode() -> None:
    print("\n" + "=" * 72)
    print("Scenario 5: Frame decoder (what tcpdump -e would show)")
    print("=" * 72)
    p = ArpPacket(ArpOp.REQUEST, "aa:bb:cc:00:00:07", "10.0.0.7",
                  ZERO_MAC, "10.0.0.9")
    f = p.frame(BCAST_MAC, "aa:bb:cc:00:00:07")
    dst = bytes_to_mac(f[0:6]); src = bytes_to_mac(f[6:12])
    etype = struct.unpack("!H", f[12:14])[0]
    decoded = ArpPacket.from_bytes(f[ETHER_HDR_LEN:])
    print(f"Ethernet: dst={dst} src={src} ethertype=0x{etype:04x}")
    print(f"ARP:      htype=1 ptype=0x0800 hlen=6 plen=4 op={ArpOp(decoded.op).name}")
    print(f"          sha={decoded.sender_ha} spa={decoded.sender_pa}")
    print(f"          tha={decoded.target_ha} tpa={decoded.target_pa}")
    print(f"frame length = {len(f)} bytes (14 Ether + 28 ARP)")


def main() -> None:
    scenario_resolution()
    scenario_gratuitous()
    scenario_proxy_arp()
    scenario_cache_aging()
    scenario_frame_decode()


if __name__ == "__main__":
    main()
