#!/usr/bin/env python3
"""Variable-sliding-window flow-control simulator (Tanenbaum Ch. 6, Fig. 6-16).

Walks the 4-bit-sequence-number example from the chapter: A requests 8
buffers, B grants 4, A sends m0..m2 (m2 is lost), B acknowledges 0+1 and
grants 3 more, A sends m3..m4, retransmits m2 on timeout, B acks through 4
with buf=0, A is blocked, B finds more buffers, and the critical line 16 --
a grant of buf=4 -- is LOST in the network. The simulator exposes the
deadlock, then applies the persist-timer fix. Pure stdlib, no network calls.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


SEQ_SPACE = 16


@dataclass
class WindowState:
    sender_credits: int = 0
    sender_next_seq: int = 0
    sender_in_flight: set[int] = field(default_factory=set)
    receiver_buffers: int = 0
    last_grant: int = 0
    deadlock: bool = False


def render(label: str, st: WindowState) -> str:
    return (
        f"  [{label:<14}] credits={st.sender_credits}  next_seq={st.sender_next_seq}  "
        f"in_flight={sorted(st.sender_in_flight)}  rcv_bufs={st.receiver_buffers}  "
        f"last_grant={st.last_grant}"
    )


def trace_figure_6_16(lost_line: int = 16) -> WindowState:
    print("=" * 72)
    print(f"VARIABLE SLIDING WINDOW  (Tanenbaum Fig. 6-16, lost_line={lost_line})")
    print("=" * 72)
    print(f"  Sequence space: {SEQ_SPACE}  (4-bit, wraps modulo 16)")
    print()

    a = WindowState()

    def step(line: str, label: str, *, lost: bool = False) -> None:
        print(f"Line {line}  {label}{'   *** LOST ***' if lost else ''}")
        print(render("A", a))

    step(" 1", "<request 8 buffers>")
    step(" 2", "<ack=15, buf=4>")
    a.sender_credits = 4
    a.last_grant = 4
    a.receiver_buffers = 4
    a.sender_credits -= 1
    a.sender_next_seq = 1
    a.sender_in_flight.add(0)
    a.receiver_buffers -= 1
    step(" 3", "<seq=0, data=m0>")
    a.sender_credits -= 1
    a.sender_next_seq = 2
    a.sender_in_flight.add(1)
    a.receiver_buffers -= 1
    step(" 4", "<seq=1, data=m1>")
    a.sender_credits -= 1
    a.sender_next_seq = 3
    a.sender_in_flight.add(2)
    step(" 5", "<seq=2, data=m2>", lost=True)
    a.sender_in_flight.discard(0)
    a.sender_in_flight.discard(1)
    a.sender_credits = 3
    a.last_grant = 3
    a.receiver_buffers = 3
    step(" 6", "<ack=1, buf=3>")
    a.sender_credits -= 1
    a.sender_next_seq = 4
    a.sender_in_flight.add(3)
    a.receiver_buffers -= 1
    step(" 7", "<seq=3, data=m3>")
    a.sender_credits -= 1
    a.sender_next_seq = 5
    a.sender_in_flight.add(4)
    a.receiver_buffers -= 1
    step(" 8", "<seq=4, data=m4>  (A blocked)")
    a.receiver_buffers -= 1
    step(" 9", "<seq=2, data=m2>  (retransmit; reserved buffer, not a new credit)")
    a.sender_in_flight.clear()
    a.sender_credits = 0
    a.last_grant = 0
    a.receiver_buffers = 0
    step("10", "<ack=4, buf=0>")
    a.sender_credits = 1
    a.last_grant = 1
    a.receiver_buffers = 1
    step("11", "<ack=4, buf=1>")
    a.sender_credits = 2
    a.last_grant = 2
    a.receiver_buffers = 2
    step("12", "<ack=4, buf=2>")
    a.sender_credits -= 1
    a.sender_next_seq = 6
    a.sender_in_flight.add(5)
    a.receiver_buffers -= 1
    step("13", "<seq=5, data=m5>")
    a.sender_credits -= 1
    a.sender_next_seq = 7
    a.sender_in_flight.add(6)
    a.receiver_buffers -= 1
    step("14", "<seq=6, data=m6>  (A blocked)")
    a.sender_credits = 0
    a.last_grant = 0
    a.receiver_buffers = 0
    step("15", "<ack=6, buf=0>")
    if lost_line == 16:
        a.sender_credits = 0
        a.last_grant = 0
        a.receiver_buffers = 4
        a.deadlock = True
        step("16", "<ack=6, buf=4>", lost=True)
        print("       A is now DEADLOCKED -- cannot tell 'no buffer' from 'grant lost'")
    else:
        a.sender_credits = 4
        a.last_grant = 4
        a.receiver_buffers = 4
        step("16", "<ack=6, buf=4>")
    return a


def apply_persist_timer(st: WindowState, max_probes: int = 3) -> int:
    print()
    print("-" * 72)
    print("PERSIST TIMER FIX  (RFC 793, also TCP_PERSIST_TIMEOUT)")
    print("-" * 72)
    for probe in range(1, max_probes + 1):
        time.sleep(0.01)
        print(f"  probe #{probe}: A sends 1-byte window-probe")
        print(f"             B replies: <ack=6, buf=4>")
        st.sender_credits = 4
        st.last_grant = 4
        st.deadlock = False
        print(f"             A.unblocked: credits={st.sender_credits}")
        if st.sender_credits > 0:
            return probe
    return max_probes


def end_to_end_argument() -> None:
    print()
    print("=" * 72)
    print("END-TO-END ARGUMENT  (Saltzer, Reed & Clark, 1984)")
    print("=" * 72)
    print("""
  A packet corrupted INSIDE a router escapes every link-layer CRC.
  The previous-hop CRC passed (the wire was clean); the next-hop CRC
  is computed over the corrupted bytes (also clean). Only an end-to-end
  check (TCP checksum, TLS MAC, IPsec AH) sees the original bytes at
  both ends and can detect the corruption.

  Implication: a correctness property (data is delivered uncorrupted)
  can ONLY be guaranteed end-to-end. Lower-layer checks are a
  performance optimisation, not a correctness guarantee.
""")


def bandwidth_delay_product() -> None:
    print("=" * 72)
    print("BANDWIDTH-DELAY PRODUCT  (the buffer size you need)")
    print("=" * 72)
    cases = [
        ("1 Mbps WAN", 1e6, 0.1),
        ("100 Mbps LAN", 100e6, 0.001),
        ("1 Gbps datacenter", 1e9, 0.0001),
        ("10 Gbps datacenter", 10e9, 0.0001),
    ]
    print(f"  {'link':<22}  {'bdp (bytes)':>14}  {'TCP window needed':>22}")
    for name, bw, rtt in cases:
        bdp = bw * rtt / 8
        if bdp <= 65535:
            window = "16-bit Window suffices"
        else:
            window = f"need Window Scale (RFC 7323)"
        print(f"  {name:<22}  {bdp:>14.1f}  {window:>22}")


def main() -> None:
    st = trace_figure_6_16(lost_line=16)
    if st.deadlock:
        probes = apply_persist_timer(st, max_probes=3)
        print(f"\n  Deadlock broken after {probes} persist-timer probe(s).")
    end_to_end_argument()
    bandwidth_delay_product()
    print()
    print("=" * 72)
    print("Lesson complete. See docs/en.md for the full dynamic-window walk,")
    print("the end-to-end argument, and TCP flow-control details.")
    print("=" * 72)


if __name__ == "__main__":
    main()
