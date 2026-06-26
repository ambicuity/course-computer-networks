#!/usr/bin/env python3
"""Transport addressing and connection establishment (Tanenbaum 6.2.1-6.2.2).

Implements:
1. TSAP/NSAP address resolution -- mapping transport endpoints (TSAPs)
   to network addresses (NSAPs) via a portmapper/directory service.
2. The three-way handshake for connection establishment (CR, ACK, DATA)
   with initial sequence numbers derived from a clock.
3. Rejection of delayed duplicate CR segments.
4. The two-army problem: proving no protocol can guarantee synchronized
   agreement over an unreliable channel.

The addressing model (Fig 6-8):
    Application -> TSAP (e.g., port 1522) -> NSAP (e.g., IP 192.168.1.1)
    Multiple TSAPs share one NSAP; the transport entity demultiplexes.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TSAP:
    host: str
    port: int

    def __repr__(self) -> str:
        return f"{self.host}:{self.port}"


@dataclass
class ServiceEntry:
    name: str
    tsap: TSAP


class Portmapper:
    def __init__(self) -> None:
        self._services: dict[str, ServiceEntry] = {}
        self._tsap_to_nsap: dict[str, str] = {}

    def register(self, name: str, tsap: TSAP, nsap: str) -> None:
        self._services[name] = ServiceEntry(name, tsap)
        self._tsap_to_nsap[str(tsap)] = nsap

    def lookup(self, name: str) -> Optional[ServiceEntry]:
        return self._services.get(name)

    def nsap_for(self, tsap: TSAP) -> Optional[str]:
        return self._tsap_to_nsap.get(str(tsap))


@dataclass
class Segment:
    kind: str
    seq: int
    ack: int
    src_tsap: Optional[TSAP] = None
    dst_tsap: Optional[TSAP] = None


class Host:
    def __init__(self, name: str, nsap: str, portmapper: Portmapper) -> None:
        self.name = name
        self.nsap = nsap
        self.portmapper = portmapper
        self.clock: int = 0
        self._connections: dict[int, dict] = {}
        self._listening: dict[int, bool] = {}
        self._inbox: list[Segment] = []
        self._outbox: list[tuple[Segment, str]] = []
        self.rejected_dupes: int = 0
        self.established: list[int] = []

    def tick(self) -> None:
        self.clock += 1

    def listen(self, port: int) -> None:
        self._listening[port] = True

    def initial_seq(self) -> int:
        return self.clock % 1000

    def connect(self, dst: Host, dst_port: int, src_port: int) -> int:
        seq = self.initial_seq()
        seg = Segment("CR", seq, 0, TSAP(self.name, src_port),
                      TSAP(dst.name, dst_port))
        self._connections[seq] = {"state": "SYN_SENT", "dst": dst, "seq": seq}
        self._outbox.append((seg, dst.nsap))
        return seq

    def deliver(self, seg: Segment, from_nsap: str) -> None:
        self._inbox.append(seg)

    def pump(self, dst: Host) -> None:
        while self._inbox:
            seg = self._inbox.pop(0)
            self._process(seg, dst)

    def _process(self, seg: Segment, peer: Host) -> None:
        if seg.kind == "CR":
            port = seg.dst_tsap.port if seg.dst_tsap else 0
            if self._listening.get(port):
                my_seq = self.initial_seq()
                conn_state = {"state": "ESTABLISHED", "peer_seq": seg.seq,
                               "my_seq": my_seq}
                self._connections[my_seq] = conn_state
                self.established.append(my_seq)
                ack_seg = Segment("ACK", my_seq, seg.seq + 1,
                                   seg.dst_tsap, seg.src_tsap)
                self._outbox.append((ack_seg, peer.nsap))
            else:
                pass
        elif seg.kind == "ACK":
            conn = self._connections.get(seg.ack - 1)
            if conn and conn["state"] == "SYN_SENT":
                conn["state"] = "ESTABLISHED"
                conn["peer_seq"] = seg.seq
                self.established.append(seg.ack - 1)
                data_seg = Segment("DATA", conn["seq"] + 1, seg.seq + 1)
                self._outbox.append((data_seg, peer.nsap))
            else:
                self.rejected_dupes += 1
        elif seg.kind == "DATA":
            pass

    def send_outbox(self, dst: Host) -> None:
        while self._outbox:
            seg, nsap = self._outbox.pop(0)
            dst.deliver(seg, self.nsap)


def run_portmapper_demo() -> None:
    print("=" * 72)
    print("Addressing: TSAP/NSAP mapping via portmapper")
    print("=" * 72)
    pm = Portmapper()

    mail_tsap = TSAP("host2", 25)
    web_tsap = TSAP("host2", 80)
    ftp_tsap = TSAP("host2", 21)
    pm.register("mail", mail_tsap, "192.168.1.2")
    pm.register("http", web_tsap, "192.168.1.2")
    pm.register("ftp", ftp_tsap, "192.168.1.2")

    print("\nService registry:")
    for name in ["mail", "http", "ftp", "unknown"]:
        entry = pm.lookup(name)
        if entry:
            nsap = pm.nsap_for(entry.tsap)
            print(f"  {name:8s} -> TSAP {entry.tsap} -> NSAP {nsap}")
        else:
            print(f"  {name:8s} -> NOT FOUND")

    print("\nKey point: Multiple TSAPs (ports) share one NSAP (IP address).")
    print("  The transport entity demultiplexes incoming segments by TSAP.")


def run_three_way_handshake() -> None:
    print("\n" + "=" * 72)
    print("Three-way handshake (normal case)")
    print("=" * 72)
    pm = Portmapper()
    host1 = Host("host1", "10.0.0.1", pm)
    host2 = Host("host2", "10.0.0.2", pm)
    host2.listen(1522)

    print("\n  Host1 clock advances to pick initial sequence number x")
    for _ in range(100):
        host1.tick()
    x = host1.initial_seq()
    print(f"  x = host1.clock % 1000 = {x}")

    print("\n  Step 1: Host1 -> Host2: CR(seq=x)")
    conn_id = host1.connect(host2, 1522, 1208)
    host1.send_outbox(host2)

    print("\n  Step 2: Host2 -> Host1: ACK(seq=y, ack=x+1)")
    host2.tick()
    host2.pump(host1)
    host2.send_outbox(host1)

    print("\n  Step 3: Host1 -> Host2: DATA(seq=x+1, ack=y+1)")
    host1.pump(host2)
    host1.send_outbox(host2)
    host2.pump(host1)

    print(f"\n  Host1 established connections: {host1.established}")
    print(f"  Host2 established connections: {host2.established}")
    assert len(host1.established) >= 1, "Connection not established on host1"
    assert len(host2.established) >= 1, "Connection not established on host2"
    print("  Three-way handshake completed successfully.")


def run_delayed_duplicate_cr() -> None:
    print("\n" + "=" * 72)
    print("Delayed duplicate CR rejected by three-way handshake")
    print("=" * 72)
    pm = Portmapper()
    host1 = Host("host1", "10.0.0.1", pm)
    host2 = Host("host2", "10.0.0.2", pm)
    host2.listen(1522)

    print("\n  Scenario (b) from Fig 6-11: stale CR arrives at host2")
    stale_cr = Segment("CR", 5, 0, TSAP("host1", 1208), TSAP("host2", 1522))
    host2.deliver(stale_cr, "10.0.0.1")
    host2.pump(host1)
    host2.send_outbox(host1)

    print("\n  Host1 is NOT expecting this ACK -> REJECT (not in SYN_SENT)")
    host1.pump(host2)
    print(f"  Host1 rejected duplicates: {host1.rejected_dupes}")
    assert host1.rejected_dupes >= 1, "Duplicate should be rejected"
    print("  The stale duplicate did no damage. Connection not established.")


def run_two_army_problem() -> None:
    print("\n" + "=" * 72)
    print("The Two-Army Problem (proving graceful agreement is impossible)")
    print("=" * 72)
    print("""
  Blue army #1 and #2 must attack simultaneously to defeat white army.
  Communication only via messengers through the valley (unreliable channel).

  Protocol attempts and why they fail:
""")

    rounds = [
        ("1-way",  1, "Blue1 sends 'attack at dawn'. Blue2 cannot be sure Blue1 got no ack, so won't attack alone."),
        ("2-way",  2, "Blue2 replies 'agreed'. But Blue2 doesn't know if reply arrived. Blue2 won't attack."),
        ("3-way",  3, "Blue1 acks the reply. But Blue1 doesn't know if its ack arrived. Blue1 hesitates."),
        ("4-way",  4, "Blue2 acks the ack. But Blue2 doesn't know if that ack arrived. Infinite regress."),
    ]

    for name, msgs, reason in rounds:
        print(f"  {name} ({msgs} messages): {reason}")
        print(f"    -> The LAST sender can NEVER be sure its message arrived.")
        print(f"    -> Therefore the LAST sender will not attack.")
        print(f"    -> The other side KNOWS this, so it won't attack either.\n")

    print("  PROOF (by contradiction): Suppose some protocol works.")
    print("  Every message is essential (remove unessential ones).")
    print("  If the LAST message is lost, the sender cannot be sure it arrived.")
    print("  So the sender won't act. The receiver knows this, so it won't act.")
    print("  Therefore NO protocol can guarantee synchronized agreement")
    print("  over an unreliable channel. QED.")
    print()
    print("  Relevance to transport: replace 'attack' with 'disconnect'.")
    print("  Graceful release (both sides agree to close) is IMPOSSIBLE to")
    print("  guarantee. In practice, we use timers and give up after N tries.")


def run_packet_lifetime() -> None:
    print("\n" + "=" * 72)
    print("Packet lifetime restriction and sequence number space")
    print("=" * 72)
    T = 120
    rates = [100, 1000, 10000, 100000]
    print(f"\n  Maximum packet lifetime T = {T}s (Internet convention)")
    print(f"  Requirement: sequence space S must satisfy S/C > T")
    print(f"  where C = clock rate (segments/sec)")
    print()
    print(f"  {'Rate (C)':>12s}  {'Min S':>10s}  {'Bits':>6s}")
    print(f"  {'-'*12}  {'-'*10}  {'-'*6}")
    import math
    for c in rates:
        min_s = c * T
        bits = math.ceil(math.log2(min_s)) if min_s > 1 else 1
        print(f"  {c:>12d}  {min_s:>10d}  {bits:>6d}")
    print()
    print("  TCP uses 32-bit sequence numbers: S = 2^32 ~ 4 billion.")
    print("  At C=1M seg/s, S/C = 4294s >> T=120s. Safe.")


def main() -> None:
    print("Addressing and Connection Establishment (Tanenbaum 6.2.1-6.2.2)")
    print()
    print("TSAP  = Transport Service Access Point (e.g., TCP port)")
    print("NSAP  = Network Service Access Point (e.g., IP address)")
    print("CR    = Connection Request segment")
    print("ACK   = Acknowledgement segment (carries initial seq + ack)")
    print()

    run_portmapper_demo()
    run_three_way_handshake()
    run_delayed_duplicate_cr()
    run_two_army_problem()
    run_packet_lifetime()

    print("\n" + "=" * 72)
    print("Summary:")
    print("  1. Portmapper maps service names -> TSAP -> NSAP")
    print("  2. Three-way handshake prevents delayed duplicate CRs")
    print("  3. Two-army problem proves graceful release cannot be guaranteed")
    print("  4. Sequence number space must satisfy S/C > T")
    print("=" * 72)


if __name__ == "__main__":
    main()