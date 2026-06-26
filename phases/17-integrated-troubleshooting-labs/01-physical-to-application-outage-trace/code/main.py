#!/usr/bin/env python3
"""Physical-to-Application Outage Trace (Integrated Troubleshooting Lab 01).

Simulates a cable cut that cascades from the physical layer up through all
five diagnostic layers (L1, L2, L3, L4, L7) and prints both the time-ordered
event trace and a bottom-up diagnostic summary.

The simulator does not sniff live traffic. It is a deterministic event
generator that models the latency each layer takes to detect and report a
fault, then walks the stack from the physical layer upward to demonstrate
the correct evidence-gathering order.

Run:  python3 main.py [--mode cable_cut|interface_flap|route_withdraw|dns_cache|silent_drop]
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Iterable


# ---------------------------------------------------------------------------
# Event record (immutable)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LayerEvent:
    """A single observable fact reported by one network layer."""

    t_seconds: float
    layer: str          # "L1", "L2", "L3", "L4", "L7"
    component: str      # e.g., "eth0", "ospfd", "tcp:443", "nginx"
    signal: str         # the counter, flag, or state name
    value: str          # the observed value
    meaning: str        # human-readable interpretation


# ---------------------------------------------------------------------------
# Layered state (intentionally mutable because it represents a real device)
# ---------------------------------------------------------------------------
@dataclass
class PhysicalState:
    name: str
    carrier: bool = True
    rx_power_dbm: float = -3.0          # 10GBASE-LR nominal
    rx_power_threshold_dbm: float = -14.0
    dom_alarm: bool = False
    transitions: int = 0


@dataclass
class DataLinkState:
    name: str
    admin_state: str = "up"
    oper_state: str = "up"
    ifInErrors: int = 0
    mac: str = "aa:bb:cc:dd:ee:01"
    fdb_flushed: int = 0


@dataclass
class NetworkState:
    iface: str
    default_route_present: bool = True
    bgp_peers_up: int = 2
    bgp_updates_sent: int = 0
    convergence_ms: float = 0.0


@dataclass
class TransportState:
    established: int = 47
    retrans: int = 0
    retrans_total: int = 0
    rtt_ms: float = 50.0
    syn_sent: int = 0
    reset_sent: int = 0


@dataclass
class ApplicationState:
    name: str = "web-server"
    port: int = 443
    listening: bool = True
    backend_healthy: bool = True
    last_http_status: int = 200
    last_error: str = ""
    dns_cache: dict[str, str] = field(default_factory=lambda: {
        "www.example.com": "93.184.216.34",
    })


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------
class CableCutSimulator:
    """Emits a deterministic event log for a configured failure mode."""

    def __init__(self, failure_mode: str = "cable_cut") -> None:
        self.failure_mode = failure_mode
        self.events: list[LayerEvent] = []
        self.phys = PhysicalState(name="eth0")
        self.dl = DataLinkState(name="eth0")
        self.net = NetworkState(iface="eth0")
        self.tx = TransportState()
        self.app = ApplicationState()

    # ----- emission helpers ------------------------------------------------
    def _emit(self, t: float, layer: str, component: str,
              signal: str, value: str, meaning: str) -> None:
        self.events.append(LayerEvent(
            t_seconds=t, layer=layer, component=component,
            signal=signal, value=value, meaning=meaning,
        ))

    # ----- layer 1 ---------------------------------------------------------
    def _l1_cable_cut(self, t: float) -> None:
        self.phys.carrier = False
        self.phys.rx_power_dbm = -40.0
        self.phys.dom_alarm = True
        self.phys.transitions += 1
        self._emit(t, "L1", "SFP+", "rx_power", "-40.0 dBm",
                   "DOM rx-power below sensitivity threshold")
        self._emit(t, "L1", "SFP+", "dom_alarm", "asserted",
                   "transceiver reports loss-of-signal")

    def _l1_interface_flap(self, t: float) -> None:
        # Two transitions within 200 ms
        self.phys.transitions += 1
        self._emit(t, "L1", "SFP+", "link", "down (flap 1/2)",
                   "transceiver toggles carrier")
        self.phys.transitions += 1
        self._emit(t + 0.2, "L1", "SFP+", "link", "down (flap 2/2)",
                   "second toggle inside debounce window")

    def _l1_silent_drop(self, t: float) -> None:
        # Physical layer remains nominal; the silent-drop is a firewall rule.
        self._emit(t, "L1", "SFP+", "rx_power", "-3.0 dBm",
                   "physical layer reports normal (no fault here)")

    # ----- layer 2 ---------------------------------------------------------
    def _l2_link_down(self, t: float) -> None:
        self.dl.oper_state = "down"
        self.dl.ifInErrors += 1
        self.dl.fdb_flushed += 1
        self._emit(t, "L2", self.dl.name, "oper_state", "DOWN",
                   "kernel flags NO-CARRIER on interface")
        self._emit(t, "L2", "bridge", "fdb_flush", "1 entry",
                   "switch FDB entry for this MAC removed")

    def _l2_normal(self, t: float) -> None:
        self._emit(t, "L2", self.dl.name, "oper_state", "UP",
                   "data link reports normal (no fault here)")

    # ----- layer 3 ---------------------------------------------------------
    def _l3_route_withdraw(self, t: float) -> None:
        self.net.default_route_present = False
        self.net.bgp_updates_sent += 2
        self.net.convergence_ms = 240.0
        self._emit(t, "L3", "ospfd", "neighbor", "10.0.0.1 DOWN",
                   "BFD: neighbor unreachable after 3×50 ms intervals")
        self._emit(t, "L3", "ospfd", "route", "0.0.0.0/0 withdrawn",
                   "default route removed from RIB; BGP UPDATE sent")

    def _l3_route_withdraw_only(self, t: float) -> None:
        # BFD/SPF-level fault, but the link is still up (e.g., silent L3 filter)
        self._emit(t, "L2", self.dl.name, "oper_state", "UP",
                   "data link is fine; route is being withdrawn anyway")
        self._l3_route_withdraw(t)

    def _l3_silent_drop(self, t: float) -> None:
        # The route exists but the next hop silently drops packets (firewall).
        self._emit(t, "L3", "ospfd", "route", "0.0.0.0/0 via 10.0.0.1",
                   "route present; L3 forwarding normal")

    # ----- layer 4 ---------------------------------------------------------
    def _l4_retransmit_climb(self, t: float) -> None:
        # Walk through three retransmissions to show the RTO cascade.
        rto = 50
        for i, dt in enumerate((0, 0.1, 0.3, 0.7, 1.5), start=0):
            self.tx.retrans = i
            self.tx.retrans_total += 1
            self._emit(t + dt, "L4", "tcp:443",
                       f"retrans({i})", f"RTO={rto}ms",
                       "TCP retransmission fires; RTO doubles per RFC 6298")
            rto = min(rto * 2, 64_000)

    def _l4_normal(self, t: float) -> None:
        self._emit(t, "L4", "tcp:443", "retrans", "0",
                   "no retransmissions; transport normal")

    # ----- layer 7 ---------------------------------------------------------
    def _l7_503(self, t: float) -> None:
        self.app.backend_healthy = False
        self.app.last_http_status = 503
        self.app.last_error = "connect() failed (110: Connection timed out)"
        self._emit(t, "L7", "nginx", "upstream_status", "503",
                   "HTTP 503 returned to client; backend marked unhealthy")
        self._emit(t, "L7", "load-balancer", "health-check", "FAIL",
                   "active health check exceeded threshold; backend removed")

    def _l7_dns_works_but_http_fails(self, t: float) -> None:
        # The lesson 02 pattern, expressed in lesson 01's stack.
        self._emit(t, "L7", "resolver", "A www.example.com",
                   "93.184.216.34 (cached, TTL=300)",
                   "DNS answers from cache; TTL not yet expired")
        self._emit(t + 0.1, "L7", "curl", "GET /", "Connection timed out",
                   "TCP connect to cached IP fails; HTTP request never sent")

    def _l7_silent_drop(self, t: float) -> None:
        # The "firewall eating packets" pattern: app sees the same 503.
        self._l7_503(t)

    # ----- dispatch --------------------------------------------------------
    def simulate(self) -> None:
        m = self.failure_mode
        if m == "cable_cut":
            self._l1_cable_cut(0.0)
            self._l2_link_down(0.0012)
            self._l3_route_withdraw(0.24)
            self._l4_retransmit_climb(2.0)
            self._l7_503(3.0)
            self._l7_dns_works_but_http_fails(5.0)
        elif m == "interface_flap":
            self._l1_interface_flap(0.0)
            self._l2_link_down(0.05)
            self._l3_route_withdraw(0.5)
            self._l4_retransmit_climb(1.5)
            self._l7_503(2.5)
        elif m == "route_withdraw":
            # L1 and L2 look fine; the fault is purely in the routing daemon.
            self._l1_silent_drop(0.0)
            self._l2_normal(0.001)
            self._l3_route_withdraw_only(0.24)
            self._l4_retransmit_climb(2.0)
            self._l7_503(3.0)
        elif m == "dns_cache":
            # Path is healthy; the "fault" is a stale DNS cache.
            self._l1_silent_drop(0.0)
            self._l2_normal(0.001)
            self._l3_silent_drop(0.24)
            self._l4_normal(2.0)
            self._l7_dns_works_but_http_fails(3.0)
        elif m == "silent_drop":
            # Firewall drops packets silently; L1, L2, L3 all look fine.
            self._l1_silent_drop(0.0)
            self._l2_normal(0.001)
            self._l3_silent_drop(0.24)
            self._l4_retransmit_climb(2.0)
            self._l7_silent_drop(3.0)
        else:
            raise ValueError(f"unknown failure mode: {m!r}")

    # ----- presentation ----------------------------------------------------
    def print_trace(self) -> None:
        print("=" * 78)
        print(f"Physical-to-Application Outage Trace  [mode={self.failure_mode}]")
        print("=" * 78)
        print(f"{'T (s)':>7}  {'L':<3}  {'component':<14}  {'signal':<22}  value")
        print("-" * 78)
        for e in self.events:
            print(f"{e.t_seconds:>7.3f}  {e.layer:<3}  {e.component:<14}  "
                  f"{e.signal:<22}  {e.value}   <- {e.meaning}")

    def print_diagnosis(self) -> None:
        print()
        print("=" * 78)
        print("BOTTOM-UP DIAGNOSIS")
        print("=" * 78)
        steps = [
            ("L1", "ip -s link show eth0",
             "NO-CARRIER, state DOWN, DOM rx_power below threshold" if not self.phys.carrier
             else "interface UP, rx_power nominal",
             "FAULT" if not self.phys.carrier else "ok"),
            ("L2", "ip neighbor; bridge fdb show",
             "FDB entry flushed for this MAC" if self.dl.oper_state == "down" else "ARP/FDB normal",
             "FAULT" if self.dl.oper_state == "down" else "ok"),
            ("L3", "ip route get 8.8.8.8",
             "default route withdrawn" if not self.net.default_route_present
             else "default route present via 10.0.0.1",
             "FAULT" if not self.net.default_route_present else "ok"),
            ("L4", "ss -ti dst 8.8.8.8",
             f"retrans climbing ({self.tx.retrans_total} total)" if self.tx.retrans_total > 0
             else "no retransmissions",
             "FAULT" if self.tx.retrans_total > 0 else "ok"),
            ("L7", "curl -v http://...",
             f"HTTP {self.app.last_http_status}: {self.app.last_error or 'ok'}"
             if self.app.last_http_status != 200
             else "HTTP 200",
             "FAULT" if self.app.last_http_status != 200 else "ok"),
        ]
        for layer, cmd, finding, status in steps:
            marker = ">>>" if status == "FAULT" else "   "
            print(f"  {marker} {layer}  $ {cmd}")
            print(f"       -> {finding}")
            print(f"       status: {status}")
            print()
        first_fault = next((s[0] for s in steps if s[3] == "FAULT"), "none")
        print(f"  First decisive evidence: layer {first_fault}")
        if first_fault == "L1":
            print("  Root cause hypothesis: physical layer fault (fiber, transceiver, port)")
        elif first_fault == "L2":
            print("  Root cause hypothesis: data link fault (MAC, FDB, bridge)")
        elif first_fault == "L3":
            print("  Root cause hypothesis: routing fault (BGP/OSPF, BFD, FIB)")
        elif first_fault == "L4":
            print("  Root cause hypothesis: path is lossy/congested or below-L4 is dropping")
        elif first_fault == "L7":
            print("  Root cause hypothesis: application fault (independent of network)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(argv: Iterable[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", default="cable_cut",
                    choices=["cable_cut", "interface_flap", "route_withdraw",
                             "dns_cache", "silent_drop"])
    args = ap.parse_args(list(argv) if argv is not None else None)
    sim = CableCutSimulator(failure_mode=args.mode)
    sim.simulate()
    sim.print_trace()
    sim.print_diagnosis()


if __name__ == "__main__":
    main()
