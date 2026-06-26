#!/usr/bin/env python3
"""Capstone 03: Debug a Realistic Outage + Build a Minimal Reliable Protocol.

Part 1: Multi-layer outage debugger with synthetic evidence.
Part 2: Minimal reliable transport (stop-and-wait with retransmission).

Run:  python3 main.py
"""
from __future__ import annotations

import random
from dataclasses import dataclass


def debug_outage() -> None:
    print("=" * 65)
    print("Part 1: Debug a Realistic Outage")
    print("=" * 65)
    evidence = [
        ("PHYSICAL", "eth0 status=down, carrier_transitions=1"),
        ("DATA LINK", "no carrier detected, link errors=5"),
        ("NETWORK", "default route withdrawn, 0 active routes"),
        ("TRANSPORT", "TCP RST on all sessions, new SYNs timeout"),
        ("APPLICATION", "HTTP 503 Service Unavailable"),
        ("DNS", "still resolves (cached) - NOT the problem"),
    ]
    print(f"\n  Evidence collected (bottom-up):\n")
    for layer, ev in evidence:
        print(f"    {layer:12s}: {ev}")
    print(f"\n  Root cause: Fiber cable cut (physical layer)")
    print(f"  Fix: Dispatch tech to splice fiber, enable backup link")


@dataclass
class Packet:
    seq: int
    data: str
    acked: bool = False


def stop_and_wait(channel_loss: float = 0.2, num_packets: int = 10, seed: int = 42) -> None:
    print(f"\n{'='*65}")
    print(f"Part 2: Minimal Reliable Protocol (Stop-and-Wait)")
    print(f"{'='*65}")
    rng = random.Random(seed)
    delivered = []
    total_transmissions = 0
    for seq in range(num_packets):
        attempts = 0
        while True:
            attempts += 1
            total_transmissions += 1
            lost = rng.random() < channel_loss
            if lost:
                print(f"  TX seq={seq} attempt={attempts} -> LOST (timeout, retransmit)")
                continue
            ack_lost = rng.random() < channel_loss
            if ack_lost:
                print(f"  TX seq={seq} attempt={attempts} -> delivered, ACK LOST (retransmit)")
                continue
            delivered.append(f"P{seq}")
            print(f"  TX seq={seq} attempt={attempts} -> delivered, ACK received OK")
            break
    print(f"\n  Delivered: {len(delivered)}/{num_packets} packets in order")
    print(f"  Total transmissions: {total_transmissions} (with retransmissions)")


def main() -> None:
    debug_outage()
    stop_and_wait()


if __name__ == "__main__":
    main()
