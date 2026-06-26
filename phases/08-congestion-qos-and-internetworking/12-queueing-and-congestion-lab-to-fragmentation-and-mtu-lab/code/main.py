#!/usr/bin/env python3
"""Queueing and Congestion Lab to Fragmentation and MTU Lab.

Stdlib-only toolkit with two tools:

1. M/M/1 queue simulator -- Poisson arrivals (lambda), exponential
   service (mu), one FIFO server. Computes theoretical metrics (rho,
   L, Lq, W, Wq) and runs a discrete-event simulation to compare.
   As rho -> 1 the queue length and wait blow up.

2. MTU discovery tool -- simulates DF-set probes across a path with
   decreasing MTUs, discovers the path MTU, fragments an oversized
   payload at that MTU, and reassembles out of order.

Run:  python3 main.py
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

HEADER = 20  # IPv4 header bytes


@dataclass
class MM1:
    """Theoretical M/M/1 metrics from lambda and mu."""
    lam: float
    mu: float
    @property
    def rho(self) -> float:
        return self.lam / self.mu
    @property
    def L(self) -> float:       # mean packets in system
        return self.rho / (1 - self.rho)
    @property
    def Lq(self) -> float:      # mean packets in queue
        return self.rho ** 2 / (1 - self.rho)
    @property
    def W(self) -> float:       # mean time in system
        return 1 / (self.mu - self.lam)
    @property
    def Wq(self) -> float:      # mean wait in queue
        return self.lam / (self.mu * (self.mu - self.lam))


def simulate_mm1(lam: float, mu: float, n: int,
                 rng: Optional[random.Random] = None) -> dict:
    """Discrete-event M/M/1 simulation; returns empirical averages."""
    rng = rng or random.Random(42)
    t = 0.0
    queue: list[float] = []
    in_svc: Optional[float] = None
    svc_end = float("inf")
    area = 0.0
    last = 0.0
    waits: list[float] = []
    services: list[float] = []
    max_q = 0
    served = 0
    next_arr = t + rng.expovariate(lam)
    gen = 0
    while served < n:
        if next_arr <= svc_end:
            t = next_arr
            area += (len(queue) + (1 if in_svc else 0)) * (t - last)
            last = t
            queue.append(t)
            gen += 1
            max_q = max(max_q, len(queue))
            next_arr = t + rng.expovariate(lam)
            if in_svc is None:
                in_svc = queue.pop(0)
                s = rng.expovariate(mu)
                services.append(s)
                svc_end = t + s
        else:
            t = svc_end
            area += (len(queue) + 1) * (t - last)
            last = t
            waits.append(t - in_svc - services[served])
            served += 1
            if queue:
                in_svc = queue.pop(0)
                s = rng.expovariate(mu)
                services.append(s)
                svc_end = t + s
            else:
                in_svc = None
                svc_end = float("inf")
    return {
        "arrivals": gen, "served": served,
        "avg_L": area / t, "avg_Wq": sum(waits) / len(waits),
        "max_q": max_q, "rho_sim": served / t,
    }


def queueing_lab() -> None:
    print("M/M/1 queue: Poisson arrivals, exponential service, 1 server.\n")
    print("  Theory:  rho=lam/mu  L=rho/(1-rho)  W=1/(mu-lam)")
    print("           Lq=rho^2/(1-rho)  Wq=lam/(mu*(mu-lam))  Little: L=lam*W\n")
    configs = [(3.0, 5.0), (4.0, 5.0), (4.5, 5.0), (4.9, 5.0)]
    print(f"  {'lam':>5} {'mu':>5} {'rho':>6} {'L':>7} {'Wq':>8}")
    for lam, mu in configs:
        m = MM1(lam, mu)
        print(f"  {lam:>5.1f} {mu:>5.1f} {m.rho:>6.2f} {m.L:>7.2f} {m.Wq:>8.3f}")
    print("\n  rho -> 1: L and Wq blow up (congestion knee at rho~0.8).\n")
    print("  Discrete-event simulation (2000 customers, seed=42):")
    print(f"  {'lam':>5} {'mu':>5} {'rho_th':>7} {'rho_sim':>8} {'L_th':>7} "
          f"{'L_sim':>8} {'max_q':>6}")
    for lam, mu in configs:
        m = MM1(lam, mu)
        r = simulate_mm1(lam, mu, 2000)
        print(f"  {lam:>5.1f} {mu:>5.1f} {m.rho:>7.2f} {r['rho_sim']:>8.2f} "
              f"{m.L:>7.2f} {r['avg_L']:>8.2f} {r['max_q']:>6}")
    print("\n  Simulated averages track theory; max_q grows sharply.\n")


@dataclass
class Fragment:
    ident: int
    offset: int    # bytes from start of original payload
    more: bool     # MF flag
    data: bytes
    def describe(self) -> str:
        return (f"id={self.ident} off={self.offset:>5} len={len(self.data):>4} "
                f"MF={'1' if self.more else '0'}")


def fragment_payload(data: bytes, mtu: int, ident: int) -> list[Fragment]:
    """Split data into IP-style fragments fitting mtu (8-byte aligned)."""
    max_p = (mtu - HEADER) // 8 * 8
    if max_p <= 0 or len(data) <= max_p:
        return [Fragment(ident, 0, False, data)]
    out: list[Fragment] = []
    off = 0
    while off < len(data):
        chunk = data[off:off + max_p]
        more = off + max_p < len(data)
        out.append(Fragment(ident, off, more, chunk))
        off += max_p
    return out


@dataclass
class Reassembler:
    ident: int
    buf: dict[int, bytes] = field(default_factory=dict)
    total: int = -1
    def add(self, f: Fragment) -> None:
        if f.ident != self.ident:
            return
        if f.offset not in self.buf:
            self.buf[f.offset] = f.data
        if not f.more:
            self.total = f.offset + len(f.data)
    def done(self) -> bool:
        if self.total < 0:
            return False
        exp = 0
        for off in sorted(self.buf):
            if off != exp:
                return False
            exp += len(self.buf[off])
        return exp == self.total
    def assemble(self) -> bytes:
        return b"".join(self.buf[o] for o in sorted(self.buf))


def mtu_lab() -> None:
    print("Path MTU Discovery: host -- R1(1400) -- R2(1200) -- R3(900) -- dest\n")
    path = [1400, 1200, 900]
    payload = bytes(2000)
    ident = 77
    discovered = 65535
    for mtu in path:
        size = len(payload) + HEADER
        if size > mtu:
            print(f"  probe {size}B DF=1 at MTU={mtu} -> DROP, ICMP Frag Needed, "
                  f"next-hop MTU={mtu}")
            discovered = min(discovered, mtu)
        else:
            print(f"  probe {size}B DF=1 at MTU={mtu} -> OK")
    print(f"\n  discovered path MTU = {discovered}B\n")
    frags = fragment_payload(payload, discovered, ident)
    print(f"  Fragment {len(payload)}B payload at MTU={discovered}: "
          f"{len(frags)} fragments")
    for f in frags:
        print(f"    {f.describe()}")
    print()
    r = Reassembler(ident=ident)
    for f in reversed(frags):
        r.add(f)
    ok = r.done() and r.assemble() == payload
    print(f"  Reassemble out of order: {'OK' if ok else 'FAIL'}\n")
    print("  Common MTUs: Ethernet=1500  802.11=2272  PPPoE=1492  IP-max=65515\n")


def main() -> None:
    print("=" * 68 + "\nQueueing and Congestion Lab\n" + "=" * 68 + "\n")
    queueing_lab()
    print("=" * 68 + "\nFragmentation and MTU Lab\n" + "=" * 68 + "\n")
    mtu_lab()
    print("=" * 68 + "\nConnecting the two\n" + "=" * 68 + "\n"
          "  Congestion = arrival rate approaches service rate: queues grow,\n"
          "  latency rises, packets drop.  Fragmentation amplifies congestion\n"
          "  because one packet becomes many fragments, each in a queue slot;\n"
          "  losing any fragment loses the whole datagram.  This is why modern\n"
          "  networks do PMTUD and avoid router fragmentation.\n\n"
          "  Checklist:\n"
          "    1. Measure lam, mu; compute rho; alert at rho > 0.8.\n"
          "    2. Discover path MTU with DF probes (ping -M do / tracepath).\n"
          "    3. If fragments appear, suspect PMTUD black hole (ICMP filtered).\n"
          "    4. Prefer RED/ECN over tail-drop to avoid TCP synchronization.")


if __name__ == "__main__":
    main()