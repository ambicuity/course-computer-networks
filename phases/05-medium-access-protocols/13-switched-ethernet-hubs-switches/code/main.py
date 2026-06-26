"""
Switched Ethernet: Hubs, Switches, Collision Domains, and Full-Duplex Links

Demonstrates:
  - Hub behavior: physical-layer repeater floods every frame to all ports
  - Switch learning: MAC forwarding table built from source addresses with aging
  - Forwarding decisions: known unicast, unknown unicast, broadcast, filtering
  - Collision domain reduction: hub = one shared domain; switch = one domain per port
  - MAC table aging: expired entries cause unknown-unicast flooding to recur
  - MAC flapping detection: same MAC appearing on two ports (loop/bonding symptom)
  - Loop hazard: broadcast frame circulates indefinitely without STP

No third-party dependencies — stdlib only.
Run:  python3 main.py
"""

import time
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BROADCAST_MAC: str = "ff:ff:ff:ff:ff:ff"
DEFAULT_AGING_SECONDS: float = 300.0   # typical vendor default (Cisco et al.)

SEP = "─" * 66
WIDE = "=" * 66


# ---------------------------------------------------------------------------
# Frame
# ---------------------------------------------------------------------------

@dataclass
class Frame:
    src: str
    dst: str
    payload: str = ""

    def __str__(self) -> str:
        dst_label = "BROADCAST" if self.dst == BROADCAST_MAC else self.dst
        return f"[{self.src} → {dst_label}] \"{self.payload}\""


# ---------------------------------------------------------------------------
# MAC Table Entry
# ---------------------------------------------------------------------------

@dataclass
class MACEntry:
    port: int
    learned_at: float   # monotonic timestamp (seconds)


# ---------------------------------------------------------------------------
# Hub — Layer 1 repeater
# ---------------------------------------------------------------------------

class Hub:
    """
    Physical-layer repeater.  No MAC awareness; regenerates every bit out of
    every port except the ingress port.  All attached stations share one half-
    duplex collision domain.
    """

    def __init__(self, name: str, num_ports: int) -> None:
        self.name = name
        self.num_ports = num_ports

    @property
    def collision_domains(self) -> int:
        return 1   # always one shared domain

    def forward(self, frame: Frame, ingress_port: int) -> list[tuple[int, str]]:
        """Return (egress_port, reason) for every port except ingress."""
        return [(p, "HUB_REPEAT") for p in range(1, self.num_ports + 1)
                if p != ingress_port]


# ---------------------------------------------------------------------------
# Switch — Layer 2 learning bridge
# ---------------------------------------------------------------------------

class Switch:
    """
    Multiport learning bridge.

    On every received frame the switch:
      1. Learns (or refreshes) the source MAC → ingress-port mapping.
      2. Decides what to do with the destination:
           - Broadcast / multicast  → flood all ports except ingress
           - Unknown unicast        → flood all ports except ingress
           - Same-port unicast      → filter (suppress)
           - Known unicast          → forward to the single learned port
    MAC table entries age out after ``aging_seconds``; a new frame to an
    aged-out destination triggers flooding again.
    """

    def __init__(self, name: str, num_ports: int,
                 aging_seconds: float = DEFAULT_AGING_SECONDS) -> None:
        self.name = name
        self.num_ports = num_ports
        self.aging_seconds = aging_seconds
        self.mac_table: dict[str, MACEntry] = {}
        self.flap_log: list[str] = []

    @property
    def collision_domains(self) -> int:
        return self.num_ports   # one isolated domain per port

    # --- Internal helpers ---------------------------------------------------

    def _now(self) -> float:
        return time.monotonic()

    def _expire_stale(self, now: float) -> list[str]:
        expired = [mac for mac, e in self.mac_table.items()
                   if (now - e.learned_at) >= self.aging_seconds]
        for mac in expired:
            del self.mac_table[mac]
        return expired

    # --- Public API ---------------------------------------------------------

    def learn(self, src_mac: str, ingress_port: int,
              now: Optional[float] = None) -> str:
        """
        Update MAC table from the source address seen on ingress_port.
        Returns a one-line description of what happened.
        """
        if now is None:
            now = self._now()
        expired = self._expire_stale(now)
        expire_note = f" (aged out: {expired})" if expired else ""

        if src_mac in self.mac_table:
            existing = self.mac_table[src_mac]
            if existing.port != ingress_port:
                msg = (f"MAC FLAP detected: {src_mac} moved "
                       f"port {existing.port} → port {ingress_port}")
                self.flap_log.append(msg)
                self.mac_table[src_mac] = MACEntry(ingress_port, now)
                return f"UPDATED(flap) {src_mac} → port {ingress_port}{expire_note}"
            self.mac_table[src_mac] = MACEntry(ingress_port, now)
            return f"REFRESHED    {src_mac} → port {ingress_port}{expire_note}"

        self.mac_table[src_mac] = MACEntry(ingress_port, now)
        return f"LEARNED      {src_mac} → port {ingress_port}{expire_note}"

    def forward(self, frame: Frame, ingress_port: int,
                now: Optional[float] = None) -> tuple[list[tuple[int, str]], str]:
        """
        Learn from source, then decide forwarding action for destination.
        Returns ([(egress_port, tag), ...], action_description).
        """
        if now is None:
            now = self._now()
        learn_log = self.learn(frame.src, ingress_port, now)

        dst = frame.dst
        if dst == BROADCAST_MAC:
            egress = [(p, "FLOOD:broadcast") for p in range(1, self.num_ports + 1)
                      if p != ingress_port]
            action = "FLOOD (broadcast — ff:ff:ff:ff:ff:ff)"
        elif dst in self.mac_table:
            dst_port = self.mac_table[dst].port
            if dst_port == ingress_port:
                egress = []
                action = "FILTER (destination on same ingress port)"
            else:
                egress = [(dst_port, "UNICAST:forward")]
                action = f"FORWARD → port {dst_port} (known unicast)"
        else:
            egress = [(p, "FLOOD:unknown") for p in range(1, self.num_ports + 1)
                      if p != ingress_port]
            action = "FLOOD (unknown unicast)"

        return egress, f"{learn_log} | {action}"

    def expire_entry(self, mac: str) -> None:
        """Manually expire one MAC entry (simulates aging timer expiry)."""
        self.mac_table.pop(mac, None)

    def table_str(self) -> str:
        if not self.mac_table:
            return "  <empty>"
        return "\n".join(f"  {mac} → port {e.port}"
                         for mac, e in sorted(self.mac_table.items()))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def print_hub_event(hub: Hub, frame: Frame, ingress_port: int,
                    host_map: dict[int, str]) -> None:
    outputs = hub.forward(frame, ingress_port)
    port_labels = ", ".join(
        f"port {p} ({host_map.get(p, '?')})" for p, _ in outputs
    )
    print(f"  Frame : {frame}")
    print(f"  Ingress: port {ingress_port} ({host_map.get(ingress_port, '?')})")
    print(f"  Egress : {port_labels}")
    print(f"  (all stations see this unicast — hub repeats everywhere)")


def print_switch_event(sw: Switch, frame: Frame, ingress_port: int,
                       host_map: dict[int, str],
                       now: Optional[float] = None) -> None:
    outputs, action = sw.forward(frame, ingress_port, now)
    print(f"  Frame  : {frame}")
    print(f"  Ingress: port {ingress_port} ({host_map.get(ingress_port, '?')})")
    print(f"  Action : {action}")
    if outputs:
        port_labels = ", ".join(
            f"port {p} ({host_map.get(p, '?')})" for p, _ in outputs
        )
        print(f"  Egress : {port_labels}")
    else:
        print("  Egress : (none — frame filtered)")
    print("  MAC table after:")
    print(sw.table_str())


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    print(WIDE)
    print("  Switched Ethernet: Hubs, Switches, and Forwarding Tables")
    print(WIDE)

    # Topology: four hosts on ports 1-4
    #   port 1 → Host A  (aa:aa:aa:aa:aa:aa)
    #   port 2 → Host B  (bb:bb:bb:bb:bb:bb)
    #   port 3 → Host C  (cc:cc:cc:cc:cc:cc)
    #   port 4 → Host D  (dd:dd:dd:dd:dd:dd)
    MAC_A = "aa:aa:aa:aa:aa:aa"
    MAC_B = "bb:bb:bb:bb:bb:bb"
    MAC_C = "cc:cc:cc:cc:cc:cc"
    MAC_D = "dd:dd:dd:dd:dd:dd"

    PORT_A, PORT_B, PORT_C, PORT_D = 1, 2, 3, 4
    host_map = {
        PORT_A: f"Host-A ({MAC_A})",
        PORT_B: f"Host-B ({MAC_B})",
        PORT_C: f"Host-C ({MAC_C})",
        PORT_D: f"Host-D ({MAC_D})",
    }

    # -----------------------------------------------------------------------
    # Part 1: Hub behavior
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("  PART 1 — Hub (Physical-Layer Repeater)")
    print(SEP)
    hub = Hub(name="HUB-1", num_ports=4)
    print(f"  Collision domains: {hub.collision_domains} (all hosts share one)")
    print()

    # A → B unicast on a hub: every port receives it
    print("  [Hub event 1] Host-A sends unicast to Host-B:")
    print_hub_event(hub, Frame(src=MAC_A, dst=MAC_B, payload="ping"), PORT_A, host_map)
    print()

    # C → D unicast cannot happen simultaneously without collision
    print("  [Hub event 2] Host-C tries to send to Host-D at the same time:")
    print("  → COLLISION: shared half-duplex medium; CSMA/CD must resolve contention")
    print()

    # -----------------------------------------------------------------------
    # Part 2: Switch — first frames, unknown-unicast flooding, learning
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("  PART 2 — Switch Learning and Forwarding Decisions")
    print(SEP)
    sw = Switch(name="SW-1", num_ports=4)
    print(f"  Collision domains: {sw.collision_domains} (one isolated domain per port)")
    print()

    t0 = 0.0   # use synthetic timestamps for reproducibility

    # Frame 1: A → B, table is empty → flood unknown unicast
    print("  [Frame 1] A → B  (table empty — unknown unicast):")
    print_switch_event(sw, Frame(src=MAC_A, dst=MAC_B, payload="hello"), PORT_A, host_map, now=t0)
    print()

    # Frame 2: B replies to A — B's MAC is unknown, A's is now known
    t1 = t0 + 0.001
    print("  [Frame 2] B → A  (B learns A's port; A's MAC now known):")
    print_switch_event(sw, Frame(src=MAC_B, dst=MAC_A, payload="hello-reply"), PORT_B, host_map, now=t1)
    print()

    # Frame 3: A → B again — both MACs learned, single-port forward
    t2 = t1 + 0.001
    print("  [Frame 3] A → B  (both learned — forward to single port, C and D are invisible):")
    print_switch_event(sw, Frame(src=MAC_A, dst=MAC_B, payload="data"), PORT_A, host_map, now=t2)
    print()

    # Frame 4: C → D — C unknown destination, D unknown too
    t3 = t2 + 0.001
    print("  [Frame 4] C → D  (C and D are new — C learned, D unknown → flood):")
    print_switch_event(sw, Frame(src=MAC_C, dst=MAC_D, payload="file"), PORT_C, host_map, now=t3)
    print()

    # Frame 5: D → C — D learned, C now known
    t4 = t3 + 0.001
    print("  [Frame 5] D → C  (D learns C; D's MAC learned; unicast to port 3):")
    print_switch_event(sw, Frame(src=MAC_D, dst=MAC_C, payload="file-ack"), PORT_D, host_map, now=t4)
    print()

    # -----------------------------------------------------------------------
    # Part 3: Broadcast — ARP
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("  PART 3 — Broadcast Flooding (ARP-like)")
    print(SEP)
    t5 = t4 + 0.001
    print("  [Frame 6] A broadcasts ARP (who has 10.0.0.2?):")
    print_switch_event(sw,
                       Frame(src=MAC_A, dst=BROADCAST_MAC, payload="ARP who-has 10.0.0.2?"),
                       PORT_A, host_map, now=t5)
    print()
    print("  Note: Switch still floods broadcasts — only a VLAN boundary or router")
    print("  can contain broadcast storms.  A hub and a switch look identical for")
    print("  broadcasts; switching reduces unicast leakage, not broadcast leakage.")
    print()

    # -----------------------------------------------------------------------
    # Part 4: Same-port filtering
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("  PART 4 — Same-Port Filtering")
    print(SEP)
    t6 = t5 + 0.001
    # Teach sw about a second station behind port 2 (hub-connected scenario)
    sw.learn(MAC_C, PORT_B, now=t6)   # pretend C is now reachable via port 2
    t7 = t6 + 0.001
    print("  [Frame 7] B → C  (C now on same port 2 as B — same-port filter):")
    print_switch_event(sw, Frame(src=MAC_B, dst=MAC_C, payload="local"), PORT_B, host_map, now=t7)
    print()

    # Restore C on its real port before next demo
    sw.learn(MAC_C, PORT_C, now=t7 + 0.001)

    # -----------------------------------------------------------------------
    # Part 5: MAC table aging → flooding returns
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("  PART 5 — MAC Table Aging (entry expiry → unknown unicast floods again)")
    print(SEP)
    print(f"  Aging timer: {sw.aging_seconds:.0f} s.  Manually expiring B's entry …")
    sw.expire_entry(MAC_B)
    print("  MAC table after expiry:")
    print(sw.table_str())
    print()
    t8 = t7 + 2.0
    print("  [Frame 8] A → B  (B's entry aged out — must flood again):")
    print_switch_event(sw, Frame(src=MAC_A, dst=MAC_B, payload="retry"), PORT_A, host_map, now=t8)
    print()

    # -----------------------------------------------------------------------
    # Part 6: MAC flapping (loop symptom)
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("  PART 6 — MAC Flapping (loop or bonding symptom)")
    print(SEP)
    print("  Simulating: same source MAC AA:AA appears on port 1, then port 3,")
    print("  then port 1 again — as would happen with an Ethernet loop.")
    print()
    flap_times = [100.0, 100.5, 101.0, 101.5]
    flap_ports = [PORT_A, PORT_C, PORT_A, PORT_C]
    for fport, ft in zip(flap_ports, flap_times):
        log = sw.learn(MAC_A, fport, now=ft)
        print(f"  t={ft:.1f}s  port={fport}: {log}")
    print()
    if sw.flap_log:
        print("  Flap events logged by switch:")
        for entry in sw.flap_log:
            print(f"    ⚠  {entry}")
    print()
    print("  Diagnosis: MAC flapping typically means an L2 loop, a misconfigured")
    print("  NIC bond, a duplicated VM MAC, or a rogue bridge.  Until resolved,")
    print("  the switch rewrites its table continuously and may flood unicast traffic.")

    # -----------------------------------------------------------------------
    # Part 7: Loop hazard — broadcast without TTL
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("  PART 7 — Loop Hazard: Broadcast Storm (no TTL in Ethernet)")
    print(SEP)

    # Model two switches connected on port 4 ↔ port 4 AND a second redundant
    # link on port 3 ↔ port 3 (a loop).  Show broadcast multiplying.
    sw_a = Switch("SW-A", num_ports=4)
    sw_b = Switch("SW-B", num_ports=4)

    loop_t = 200.0
    broadcast_frame = Frame(src=MAC_A, dst=BROADCAST_MAC, payload="ARP")

    print("  Topology: SW-A port4 ↔ SW-B port4  AND  SW-A port3 ↔ SW-B port3 (LOOP!)")
    print("  Host-A (port 1 on SW-A) sends one ARP broadcast.")
    print()

    copies = 1
    for iteration in range(1, 5):
        loop_t += 0.001
        # Each switch floods the broadcast out all other ports, including the
        # redundant link, which sends it back, which gets flooded again.
        egress_a, _ = sw_a.forward(broadcast_frame, ingress_port=1, now=loop_t)
        new_copies = copies * len(egress_a)   # rough amplification model
        print(f"  Loop iteration {iteration}: {copies} frame(s) in → "
              f"{new_copies} frame(s) out (flooded to {len(egress_a)} ports each)")
        copies = new_copies

    print()
    print(f"  After {iteration} iterations: {copies} frames circulating.")
    print("  Ethernet has no TTL field.  Without Spanning Tree Protocol (STP)")
    print("  or storm-control, broadcast frames multiply until the network collapses.")

    # -----------------------------------------------------------------------
    # Summary table
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("  SUMMARY: Collision Domains and Broadcast Domains")
    print(SEP)
    headers = ["Device", "Collision Domains", "Broadcast Domains", "Unicast Privacy"]
    rows = [
        ["Hub (4-port)",    "1 (all shared)",   "1",            "None (hub repeats all)"],
        ["Switch (4-port)", "4 (one per port)", "1 per VLAN",   "Yes (unicast narrowed)"],
        ["Router",          "N (one per port)", "One per iface","Yes (routes, not bridges)"],
    ]
    col_w = [max(len(h), max(len(r[i]) for r in rows)) + 2
             for i, h in enumerate(headers)]
    header_line = "  " + "  ".join(h.ljust(col_w[i]) for i, h in enumerate(headers))
    print(header_line)
    print("  " + "  ".join("─" * w for w in col_w))
    for row in rows:
        print("  " + "  ".join(row[i].ljust(col_w[i]) for i in range(len(headers))))
    print()

    # -----------------------------------------------------------------------
    # Duplex mismatch explanation
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("  DUPLEX MISMATCH — Symptom Explanation")
    print(SEP)
    print("  Full-duplex link: separate TX/RX paths; no shared medium; CSMA/CD disabled.")
    print("  Half-duplex link: shared medium; CSMA/CD active; collisions are normal.")
    print()
    print("  Mismatch scenario (switch port = full-duplex; NIC = half-duplex):")
    print("    Half-duplex NIC detects collision while switch keeps transmitting.")
    print("    → NIC: collision counter increments, exponential backoff, retransmit")
    print("    → Switch: sees FCS/CRC errors from truncated frames, may drop silently")
    print("    → Throughput: collapses asymmetrically (upload vs download differ)")
    print("    → Symptom: terrible throughput, late collisions on one side,")
    print("               CRC errors on the other, no obvious physical failure")
    print()
    print("  Diagnosis: check NIC and switch port auto-negotiation settings;")
    print("  set both sides to the same speed/duplex explicitly if auto-neg fails.")
    print()


if __name__ == "__main__":
    main()
