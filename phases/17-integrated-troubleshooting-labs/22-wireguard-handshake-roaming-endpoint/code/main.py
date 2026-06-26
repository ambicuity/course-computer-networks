#!/usr/bin/env python3
"""WireGuard handshake and roaming diagnostic.

Reference oracle for the integrated troubleshooting lab. Walks the
Noise IKpsk2 handshake state machine and the roaming logic, then
prints the verdict that matches the production `wg show` output.

Scenarios:

  handshake_fail
    The Noise handshake never completes; wg show reports
    'latest handshake: never'. Misconfiguration: wrong public
    key, wrong endpoint, or wrong AllowedIPs.

  roam_breaks
    The client moved networks, persistentkeepalive is off, the
    kernel's cached endpoint is stale, and the first packet from
    the new source is dropped until the rekey timer fires.

  roam_works
    persistentkeepalive is on, the kernel updates the endpoint
    every 25 s, and roaming is seamless.

  allowed_ips_mismatch
    The server's AllowedIPs is too narrow; the client sends
    a packet for an IP outside the list; the server drops it
    silently.

Run:  python3 main.py --scenario roam_breaks
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field


@dataclass(frozen=True)
class WireGuardPacket:
    """A synthetic WireGuard transport / handshake packet."""

    t_seconds: float
    type_: int  # 1 = init, 2 = response, 3 = cookie, 4 = transport
    sender_index: int
    receiver_index: int
    note: str


@dataclass
class PeerState:
    endpoint: str = "(none)"
    latest_handshake_seconds: float = -1.0
    transfer_rx: int = 0
    transfer_tx: int = 0
    persistent_keepalive: int = 0
    allowed_ips: tuple[str, ...] = ()


def simulate(scenario: str) -> tuple[list[WireGuardPacket], PeerState, list[str]]:
    packets: list[WireGuardPacket] = []
    state = PeerState()
    notes: list[str] = []
    t = 0.0

    if scenario == "handshake_fail":
        notes.append("wg show reports 'latest handshake: never'.")
        notes.append("Likely causes: wrong server public key, wrong endpoint, ")
        notes.append("firewall blocking UDP 51820, AllowedIPs mismatch on the server.")
    elif scenario == "roam_breaks":
        state.endpoint = "203.0.113.42:43210"
        state.latest_handshake_seconds = 1800.0
        state.transfer_rx = 1_200_000
        state.persistent_keepalive = 0
        t += 1800.0
        notes.append("Client moved from 203.0.113.42:43210 to 198.51.100.91:55001.")
        notes.append("persistentkeepalive is 0 (off); kernel keeps the cached endpoint.")
        t += 1.0
        notes.append("Client sends a packet from new source to cached endpoint.")
        notes.append("Server's view of client is still the old endpoint; receiver_index")
        notes.append("is bound to the old session; packet is dropped until rekey timer.")
        notes.append("Rekey default = 120 s. Effective stall: up to 2 minutes.")
    elif scenario == "roam_works":
        state.endpoint = "203.0.113.42:43210"
        state.latest_handshake_seconds = 5.0
        state.transfer_rx = 1_200_000
        state.persistent_keepalive = 25
        t += 25.0
        packets.append(WireGuardPacket(t, 4, sender_index=0xDEADBEEF, receiver_index=0x12345678,
                                        note="empty transport, refreshes endpoint"))
        t += 25.0
        notes.append("Client moved to 198.51.100.91:55001.")
        notes.append("Next persistentkeepalive at t+25 carries the new source;")
        notes.append("server updates its view; the next data packet is delivered.")
    elif scenario == "allowed_ips_mismatch":
        state.endpoint = "203.0.113.42:43210"
        state.latest_handshake_seconds = 5.0
        state.allowed_ips = ("10.0.0.5/32",)
        notes.append("Server's AllowedIPs for the peer is 10.0.0.5/32.")
        notes.append("Client sends a packet to 10.0.0.6; server drops it silently")
        notes.append("because 10.0.0.6 is not in the AllowedIPs list.")
        notes.append("Fix: add 10.0.0.0/24 to the peer's AllowedIPs in wg0.conf.")
    else:
        notes.append(f"Unknown scenario: {scenario}")
    return packets, state, notes


def render(scenario: str, packets: list[WireGuardPacket], state: PeerState, notes: list[str]) -> str:
    out: list[str] = []
    out.append("=" * 64)
    out.append(f"WIREGUARD ORACLE  --  scenario: {scenario}")
    out.append("=" * 64)
    out.append("")
    out.append("wg show wg0 (peer state):")
    out.append(f"  endpoint            : {state.endpoint}")
    out.append(f"  latest handshake    : {state.latest_handshake_seconds} seconds ago"
               if state.latest_handshake_seconds >= 0 else "  latest handshake    : never")
    out.append(f"  transfer            : {state.transfer_rx} bytes received, "
               f"{state.transfer_tx} bytes sent")
    out.append(f"  persistent keepalive: "
               f"every {state.persistent_keepalive} seconds"
               if state.persistent_keepalive > 0 else "  persistent keepalive: off")
    if state.allowed_ips:
        out.append(f"  allowed ips         : {list(state.allowed_ips)}")
    out.append("")
    if packets:
        out.append("WireGuard packets observed:")
        out.append(f"{'t (s)':>8}  {'type':<6}  note")
        out.append("-" * 60)
        for p in packets:
            out.append(f"{p.t_seconds:>8.2f}  {p.type_:<6}  {p.note}")
        out.append("")
    out.append("Verdict:")
    for n in notes:
        out.append(f"  - {n}")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--scenario",
        choices=("handshake_fail", "roam_breaks", "roam_works", "allowed_ips_mismatch"),
        default="roam_breaks",
    )
    args = parser.parse_args()
    packets, state, notes = simulate(args.scenario)
    print(render(args.scenario, packets, state, notes))


if __name__ == "__main__":
    main()
