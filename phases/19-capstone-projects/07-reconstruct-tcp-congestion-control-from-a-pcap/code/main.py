#!/usr/bin/env python3
"""Capstone 07: Reconstruct TCP Congestion Control from a Pcap.

Synthesizes a TCP segment trace from a deterministic Reno sender, then
reconstructs the cwnd trajectory purely from seq/ack/timestamp/flags.
The reconstruction is compared sample-by-sample against a reference Reno model.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

MSS, RTT = 1460, 0.030


class Phase(Enum):
    SS = "Slow Start"
    CA = "Congestion Avoidance"
    FR = "Fast Recovery"
    TO = "Timeout"


class Loss(Enum):
    NONE = "No Loss"
    DUP = "Triple Dup-ACK"
    RTO = "RTO Timeout"


@dataclass
class Seg:
    t: float
    sip: str; sp: int; dip: str; dp: int
    seq: int; ack: int
    fl: str; plen: int; win: int = 65535
    rtx: bool = False


def S(t, sip, sp, dip, dp, seq, ack, fl, plen=0, rtx=False):
    return Seg(t, sip, sp, dip, dp, seq, ack, fl, plen, 65535, rtx)


# ---------- Synthetic trace generator ----------
def gen() -> list[Seg]:
    cs, ss = "10.0.0.5", "10.0.0.10"
    cp, sp_ = 50000, 80
    segs = [S(0, cs, cp, ss, sp_, 0, 0, "S"),
            S(RTT/2, ss, sp_, cs, cp, 0, 1, "SA"),
            S(RTT, cs, cp, ss, sp_, 1, 1, "A")]
    t, ns, aseq = RTT + 0.002, 1, 1
    cwnd, ssth = 1, 8

    def burst(cw, t0):
        nonlocal ns, aseq, t
        out = []
        for i in range(cw):
            seq = ns + i * MSS
            out.append(S(t0 + i * 0.0001, cs, cp, ss, sp_,
                         seq, aseq, "PA", MSS))
        at = t0 + RTT / 2
        for i in range(cw):
            an = ns + (i + 1) * MSS
            out.append(S(at + i * 0.0001, ss, sp_, cs, cp, an, an, "A"))
        ns += cw * MSS
        return out, at + 0.001

    # RTTs 0-3 slow-start (1,2,4 capped at ssthresh=8)
    for _ in range(4):
        b, t = burst(cwnd, t); segs += b
        cwnd = min(cwnd * 2, ssth)
    # RTTs 4-8 congestion avoidance
    for _ in range(5):
        b, t = burst(cwnd, t); segs += b
        cwnd += 1
    # RTT 9 triplicate-ACK
    lost = ns + 3 * MSS
    for i in range(cwnd):
        segs.append(S(t + i * 0.0001, cs, cp, ss, sp_,
                      ns + i * MSS, aseq, "PA", MSS))
    at = t + RTT / 2
    aseq = ns + 3 * MSS
    for _ in range(4):
        segs.append(S(at, ss, sp_, cs, cp, aseq, aseq, "A"))
    ssth = max(cwnd // 2, 2); cwnd = ssth
    t = at + 0.001
    segs.append(S(t, cs, cp, ss, sp_, lost, aseq, "PA", MSS, rtx=True))
    aseq = ns + cwnd * MSS
    segs.append(S(t + RTT / 2, ss, sp_, cs, cp, aseq, aseq, "A"))
    ns += cwnd * MSS
    t += RTT / 2 + 0.001
    # RTTs 10-15 congestion avoidance
    for _ in range(6):
        b, t = burst(cwnd, t); segs += b
        cwnd += 1
    # RTT 16 timeout: send a burst that gets no ACKs, then retransmit
    first = ns
    burst_n = cwnd
    for i in range(burst_n):
        segs.append(S(t + i * 0.0001, cs, cp, ss, sp_,
                      ns + i * MSS, aseq, "PA", MSS))
    tr = t + RTT * 2
    ssth = max(burst_n // 2, 2); cwnd = 1
    segs.append(S(tr, cs, cp, ss, sp_, first, aseq, "PA", MSS, rtx=True))
    aseq = first + burst_n * MSS
    segs.append(S(tr + RTT / 2, ss, sp_, cs, cp, aseq, aseq, "A"))
    ns = aseq
    t = tr + RTT / 2 + 0.001
    # RTTs 17-24 recovery (slow start then CA)
    for _ in range(8):
        b, t = burst(cwnd, t); segs += b
        cwnd = cwnd * 2 if cwnd < ssth else cwnd + 1

    return sorted(segs, key=lambda x: x.t)


# ---------- Reconstruction ----------
def srtt(segs, cp):
    data = [s for s in segs if s.sp == cp and s.plen > 0 and not s.rtx]
    acks = [s for s in segs if s.dp == cp and s.fl == "A"]
    smp, done = [], set()
    for d in data:
        if d.seq in done:
            continue
        tgt = d.seq + d.plen
        for a in acks:
            if a.t > d.t and a.ack >= tgt:
                smp.append(a.t - d.t); done.add(d.seq); break
    if not smp: return RTT
    s = smp[0]
    for r in smp[1:]:
        s = 0.875 * s + 0.125 * r
    return s


def loss_evt(segs, cp):
    acks = [s for s in segs if s.dp == cp and "A" in s.fl]
    ev = []
    last, dup = -1, 0
    for a in acks:
        if a.ack == last and a.ack > 0:
            dup += 1
            if dup == 3:
                ev.append((Loss.DUP, a.t))
        else:
            dup = 0
        last = a.ack
    lt = 0.0
    for a in acks:
        if lt and a.t - lt > 0.060:
            ev.append((Loss.RTO, a.t))
        lt = a.t
    return ev


def recon(segs, cp, sr):
    data = [s for s in segs if s.sp == cp and s.plen > 0]
    acks = [s for s in segs if s.dp == cp and "A" in s.fl]
    if not data:
        return [], []
    ev = loss_evt(segs, cp)
    s0, s1 = data[0].t, data[-1].t
    n = int((s1 - s0) / sr) + 1
    out, ssth, in_ss = [], None, True
    for i in range(n):
        rs = s0 + i * sr
        re = s0 + (i + 1) * sr
        hs = max((d.seq + d.plen for d in data if d.t < re), default=0)
        ha = max((a.ack for a in acks if a.t < re), default=0)
        fl = max(0, hs - ha)
        cw = fl / MSS
        loss = Loss.NONE
        for ev_ty, ev_t in ev:
            if rs <= ev_t < re:
                loss = ev_ty
                ssth = max(cw / 2, 2)
                if ev_ty == Loss.RTO:
                    in_ss = True
                break
        if loss == Loss.RTO:
            ph = Phase.TO; in_ss = True
        elif loss == Loss.DUP:
            ph = Phase.FR
        elif ssth is not None and cw >= ssth:
            ph = Phase.CA; in_ss = False
        elif in_ss:
            ph = Phase.SS
        else:
            ph = Phase.CA
        out.append((i, cw, ph, ssth, loss))
    return out, ev


def ref_reno(ev, sr, n):
    cw = 1.0
    ssth = 8.0  # initial threshold matches the synthetic trace generator
    ph = Phase.SS
    out = []
    lt = sorted([t for _, t in ev])
    for i in range(n):
        loss = Loss.NONE
        for lt_ in lt:
            if abs(lt_ - i * sr) < sr:
                ty = next(x for x in ev if x[1] == lt_)[0]
                loss = ty
                if ty == Loss.DUP:
                    ssth = max(cw / 2, 2); cw = ssth; ph = Phase.FR
                else:
                    ssth = max(cw / 2, 2); cw = 1.0; ph = Phase.TO
                break
        out.append((i, cw, ph, ssth, loss))
        if loss == Loss.NONE:
            if ph == Phase.SS:
                cw = min(cw * 2, ssth)
                if cw >= ssth:
                    ph = Phase.CA
            elif ph == Phase.CA:
                cw += 1
            elif ph == Phase.FR:
                ph = Phase.CA
                cw = ssth if ssth else cw
            elif ph == Phase.TO:
                ph = Phase.SS
    return out


def main():
    segs = gen()
    cp = 50000
    sr = srtt(segs, cp)
    rec, ev = recon(segs, cp, sr)
    rf = ref_reno(ev, sr, len(rec))
    n = min(len(rec), len(rf))
    mae = sum(abs(rec[i][1] - rf[i][1]) for i in range(n)) / n
    pa = sum(1 for i in range(n) if rec[i][2] == rf[i][2]) / n * 100
    print("Capstone 07: TCP Congestion Control Reconstruction")
    print(f"segments={len(segs)} SRTT={sr*1000:.1f}ms events={len(ev)} rtts={len(rec)}")
    print(f"MAE={mae:.2f}MSS phase_agreement={pa:.1f}%")
    print(f"{'RTT':>3} {'recon':>8} {'ref':>8} {'recon_phase':<22} {'ref_phase':<22}")
    for i in range(n):
        print(f"{rec[i][0]:>3} {rec[i][1]:>8.1f} {rf[i][1]:>8.1f} "
              f"{rec[i][2].value:<22} {rf[i][2].value:<22}")


if __name__ == "__main__":
    main()
