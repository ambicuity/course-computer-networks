"""LAN-to-WAN toolkit: scale classifier, Ethernet frame parser, a self-learning
switch (with a broadcast-storm demo), and a WAN-option comparator.

Everything here is stdlib-only and offline. It illustrates the lesson
"Local Area Networks to Wide Area Networks":

  * classify_by_distance()  -> PAN / LAN / MAN / WAN by interprocessor distance
  * parse_ethernet_frame()  -> decode dst/src MAC, EtherType, payload from hex
  * Switch                  -> IEEE 802.3 learning switch: learn, forward, flood
  * broadcast_storm_demo()  -> why a loop with no spanning tree is fatal
  * compare_wan_options()   -> leased line vs. VPN vs. ISP trade-offs

Run:  python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# --- Scale classification (Tanenbaum, Computer Networks, Fig. 1-6) -----------

BROADCAST_MAC = "ff:ff:ff:ff:ff:ff"
ETHERTYPES = {0x0800: "IPv4", 0x0806: "ARP", 0x86DD: "IPv6", 0x8100: "802.1Q VLAN"}
MAC_AGING_SECONDS = 300  # default Ethernet forwarding-table aging time


def classify_by_distance(metres: float) -> tuple[str, str]:
    """Map an interprocessor distance to a network scale and dominant standard."""
    if metres <= 1:
        return "PAN", "Bluetooth (IEEE 802.15.1) / RFID"
    if metres <= 1_000:
        return "LAN", "Ethernet (IEEE 802.3) / Wi-Fi (IEEE 802.11)"
    if metres <= 50_000:
        return "MAN", "Cable/DOCSIS / WiMAX (IEEE 802.16)"
    if metres <= 10_000_000:
        return "WAN", "Leased lines + routers / SONET / MPLS"
    return "Internetwork", "IP over everything (the Internet)"


# --- Ethernet frame parsing (IEEE 802.3, DIX header) -------------------------


@dataclass
class EthernetFrame:
    dst_mac: str
    src_mac: str
    ethertype: int
    payload: bytes

    @property
    def ethertype_name(self) -> str:
        return ETHERTYPES.get(self.ethertype, f"0x{self.ethertype:04X}")

    @property
    def is_broadcast(self) -> bool:
        return self.dst_mac == BROADCAST_MAC  # all-ones destination address


def _format_mac(raw: bytes) -> str:
    return ":".join(f"{b:02x}" for b in raw)


def parse_ethernet_frame(hex_string: str) -> EthernetFrame:
    """Parse a hex string (no preamble/SFD/FCS) into an EthernetFrame.

    Layout: 6 bytes dst | 6 bytes src | 2 bytes EtherType | payload.
    A standard frame payload is 46-1500 bytes; we do not enforce the floor here.
    """
    data = bytes.fromhex(hex_string.replace(" ", "").replace(":", ""))
    if len(data) < 14:
        raise ValueError(f"frame too short: {len(data)} bytes, need >= 14 header")
    dst = _format_mac(data[0:6])
    src = _format_mac(data[6:12])
    ethertype = int.from_bytes(data[12:14], "big")
    payload = data[14:]
    return EthernetFrame(dst_mac=dst, src_mac=src, ethertype=ethertype, payload=payload)


def build_ethernet_frame(dst: str, src: str, ethertype: int, payload: bytes) -> str:
    """Build a hex frame from fields (inverse of parse_ethernet_frame)."""
    dst_b = bytes.fromhex(dst.replace(":", ""))
    src_b = bytes.fromhex(src.replace(":", ""))
    return (dst_b + src_b + ethertype.to_bytes(2, "big") + payload).hex()


# --- IEEE 802.3 learning switch ----------------------------------------------


@dataclass
class Switch:
    """A self-learning Layer-2 switch.

    Learns (src MAC -> arrival port) and forwards by dst MAC. On a table miss
    or a broadcast destination it floods out every port except the ingress.
    """

    num_ports: int
    name: str = "sw1"
    # mac -> (port, last_seen_tick)
    table: dict[str, tuple[int, int]] = field(default_factory=dict)
    flood_count: int = 0
    forward_count: int = 0
    _tick: int = 0

    def deliver(self, src: str, dst: str, in_port: int) -> str:
        """Process one frame; return a human-readable action description."""
        if not 1 <= in_port <= self.num_ports:
            raise ValueError(f"in_port {in_port} outside 1..{self.num_ports}")
        self._tick += 1

        # 1. Learn the source on its ingress port (refresh on every frame).
        self.table[src] = (in_port, self._tick)

        # 2. Decide based on the destination.
        if dst == BROADCAST_MAC:
            self.flood_count += 1
            return self._flood(in_port, reason="broadcast")

        entry = self.table.get(dst)
        if entry is None:
            self.flood_count += 1
            return self._flood(in_port, reason="unknown-unicast")

        out_port, _ = entry
        if out_port == in_port:
            return f"DROP  (dst {dst} is on ingress port {in_port}; same-port)"
        self.forward_count += 1
        return f"FORWARD {src}->{dst} out port {out_port}"

    def _flood(self, in_port: int, reason: str) -> str:
        out_ports = [p for p in range(1, self.num_ports + 1) if p != in_port]
        return f"FLOOD ({reason}) out ports {out_ports}"

    def dump_table(self) -> list[str]:
        rows = ["  MAC                port   age(ticks)"]
        for mac, (port, seen) in sorted(self.table.items()):
            rows.append(f"  {mac}  {port:^5}  {self._tick - seen}")
        return rows


# --- Broadcast-storm demonstration -------------------------------------------


def broadcast_storm_demo(loop_present: bool, hops: int = 6) -> int:
    """Model frame replication of one broadcast around a switch loop.

    With no spanning tree, each switch re-floods the broadcast to its neighbour
    and nothing decrements it (Ethernet has no TTL) -> unbounded growth. We cap
    the simulation at `hops` to keep it finite and report the frame count.
    With STP a redundant port is blocked, so the broadcast is delivered once.
    """
    if not loop_present:
        return 1  # STP blocks the redundant port: delivered once, no storm.

    frames = 1
    for _ in range(hops):
        frames *= 2  # each switch in the loop duplicates onto the other path
    return frames


# --- WAN option comparison ----------------------------------------------------


def compare_wan_options() -> list[tuple[str, str, str, str]]:
    """Return (option, control, flexibility, example one-way latency) rows."""
    return [
        ("Dedicated leased line", "Full (guaranteed capacity)",
         "Low (new circuit per office pair)", "~20 ms, stable"),
        ("VPN over Internet", "None over underlying path",
         "High (reuse one Internet link)", "~35 ms, variable jitter/loss"),
        ("ISP network (3rd-party subnet)", "Provider SLA",
         "Medium (buy reach, not build)", "~25 ms, per provider SLA"),
    ]


# --- Demonstration ------------------------------------------------------------


def main() -> None:
    print("=" * 68)
    print("1. CLASSIFY BY SCALE (interprocessor distance -> network type)")
    print("=" * 68)
    for metres in (1, 100, 800, 10_000, 5_000_000, 12_000_000):
        kind, std = classify_by_distance(metres)
        print(f"  {metres:>12,} m  ->  {kind:<13} {std}")

    print("\n" + "=" * 68)
    print("2. PARSE AN ETHERNET FRAME (IEEE 802.3)")
    print("=" * 68)
    hexf = build_ethernet_frame(
        dst="ff:ff:ff:ff:ff:ff", src="00:1a:2b:3c:4d:5e",
        ethertype=0x0806, payload=b"ARP who-has 10.0.0.5")
    frame = parse_ethernet_frame(hexf)
    print(f"  dst MAC   : {frame.dst_mac}  (broadcast={frame.is_broadcast})")
    print(f"  src MAC   : {frame.src_mac}")
    print(f"  EtherType : {frame.ethertype_name}")
    print(f"  payload   : {len(frame.payload)} bytes")

    print("\n" + "=" * 68)
    print("3. SELF-LEARNING SWITCH: learn, forward, flood")
    print("=" * 68)
    sw = Switch(num_ports=4, name="access-sw")
    a, b, c = "00:00:00:00:00:0a", "00:00:00:00:00:0b", "00:00:00:00:00:0c"
    traffic = [
        (a, b, 1),               # B unknown -> flood, learn A on port 1
        (b, a, 2),               # A known on port 1 -> forward, learn B on port 2
        (a, b, 1),               # B now known on port 2 -> forward
        (c, BROADCAST_MAC, 3),   # broadcast -> flood, learn C on port 3
    ]
    for src, dst, port in traffic:
        action = sw.deliver(src, dst, port)
        print(f"  in:p{port}  {src[-2:]}->{dst[-2:] if dst != BROADCAST_MAC else 'ff'}  {action}")
    print(f"\n  table after traffic (floods={sw.flood_count}, "
          f"forwards={sw.forward_count}):")
    for row in sw.dump_table():
        print(row)

    print("\n" + "=" * 68)
    print("4. BROADCAST STORM: loop without spanning tree (IEEE 802.1D)")
    print("=" * 68)
    with_stp = broadcast_storm_demo(loop_present=False)
    no_stp = broadcast_storm_demo(loop_present=True, hops=8)
    print(f"  STP blocking redundant port : 1 broadcast delivered {with_stp} time")
    print(f"  loop, no STP (8 hops)       : {no_stp:,} frames -- the storm")
    print("  evidence: switch CPU ~100%, links at line rate, MAC table flapping")

    print("\n" + "=" * 68)
    print("5. WAN OPTIONS: leased line vs. VPN vs. ISP")
    print("=" * 68)
    print(f"  {'option':<32}{'control':<28}{'latency'}")
    for opt, control, _flex, latency in compare_wan_options():
        print(f"  {opt:<32}{control:<28}{latency}")


if __name__ == "__main__":
    main()
