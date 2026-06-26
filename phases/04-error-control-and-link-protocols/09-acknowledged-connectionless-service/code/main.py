"""
Acknowledged connectionless data link service — stop-and-wait ARQ simulator.

Models the middle of the three data-link service classes (the textbook's
Section 3.1.1): no connection setup, but each frame is individually
acknowledged and retransmitted on timeout. Uses a 1-bit sequence number
(stop-and-wait), CRC-32 error detection, and a configurable retransmission
timer.

The simulator is deterministic: the channel is driven in lockstep so a
scenario replays identically every run. Stdlib only — no network calls.
"""

import struct
import zlib
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Frame layout: type(1) | seq(1) | len(2) | payload(len) | crc32(4)
# ---------------------------------------------------------------------------

TYPE_DATA = 0
TYPE_ACK = 1


@dataclass
class Frame:
    type: int
    seq: int
    payload: bytes = b""

    def serialize(self) -> bytes:
        header = struct.pack(">BBH", self.type, self.seq, len(self.payload))
        body = header + self.payload
        crc = zlib.crc32(body) & 0xFFFFFFFF
        return body + struct.pack(">I", crc)

    @staticmethod
    def parse(raw: bytes) -> "Frame | None":
        """Return a Frame if the CRC checks, else None (silent discard)."""
        if len(raw) < 8:  # 4 header + 4 crc, empty payload
            return None
        body, crc_bytes = raw[:-4], raw[-4:]
        (crc_recv,) = struct.unpack(">I", crc_bytes)
        if zlib.crc32(body) & 0xFFFFFFFF != crc_recv:
            return None
        if len(body) < 4:
            return None
        ftype, seq, plen = struct.unpack(">BBH", body[:4])
        payload = body[4:]
        if len(payload) != plen:
            return None
        return Frame(ftype, seq, payload)


# ---------------------------------------------------------------------------
# Sender and Receiver running stop-and-wait, driven in lockstep.
# ---------------------------------------------------------------------------

@dataclass
class Sender:
    name: str = "S"
    seq: int = 0
    max_retries: int = 5
    delivered: list = field(default_factory=list)


@dataclass
class Receiver:
    name: str = "R"
    expected: int = 0  # the next sequence bit it wants
    delivered: list = field(default_factory=list)
    duplicates: int = 0


# ---------------------------------------------------------------------------
# Deterministic driver. drop_data / drop_ack are 0-based indices in their
# own direction's frame stream. A dropped DATA means the receiver never sees
# it (so never ACKs); a dropped ACK means the sender times out and resends,
# which the receiver then sees as a duplicate (or, if it rebooted, as fresh).
# ---------------------------------------------------------------------------

def simulate(records: list[bytes],
             drop_data: set[int] | None = None,
             drop_ack: set[int] | None = None,
             receiver_reset_after: int | None = None) -> dict:
    drop_data = drop_data or set()
    drop_ack = drop_ack or set()
    s = Sender()
    r = Receiver()
    trace: list[str] = []

    data_counter = 0
    ack_counter = 0

    for i, rec in enumerate(records):
        trace.append(f"=== record {i}: {rec!r} ===")
        retry = 0
        sender_acked = False  # the sender advances only when it gets a valid ACK
        # The reboot hazard: after the receiver has accepted the original and the
        # ACK is lost, the receiver loses `expected` before the retransmission
        # arrives -- so it mistakes the resend for a fresh frame.
        pending_reset = False
        reset_armed = (receiver_reset_after is not None and i == receiver_reset_after)

        while retry <= s.max_retries and not sender_acked:
            this_seq = s.seq
            trace.append(f"  S TX DATA seq={this_seq} retry={retry} (d-idx {data_counter})")
            data_idx = data_counter
            data_counter += 1

            if data_idx in drop_data:
                trace.append(f"  channel DROPPED data d-idx {data_idx} -> S times out")
            else:
                # Receiver gets the DATA frame.
                if reset_armed and retry >= 1 and not pending_reset:
                    trace.append("  R rebooted between original and resend: expected <- 0")
                    r.expected = 0
                    pending_reset = True

                if this_seq == r.expected:
                    trace.append(f"  R accept seq={this_seq}, deliver up, "
                                 f"expected <- {this_seq ^ 1}")
                    r.delivered.append(rec)
                    r.expected ^= 1
                else:
                    r.duplicates += 1
                    trace.append(f"  R DUPLICATE seq={this_seq} (want {r.expected}), "
                                 "discard payload, re-ACK")

                # Receiver always (re-)ACKs the next expected sequence.
                trace.append(f"  R TX ACK seq={r.expected} (a-idx {ack_counter})")
                ack_idx = ack_counter
                ack_counter += 1
                if ack_idx in drop_ack:
                    trace.append(f"  channel DROPPED ack a-idx {ack_idx} -> S times out")
                else:
                    trace.append(f"  S got ACK seq={r.expected} -> advance seq <- {this_seq ^ 1}")
                    s.delivered.append(rec)
                    s.seq ^= 1
                    sender_acked = True

            if not sender_acked:
                retry += 1
                trace.append(f"  S timeout, retransmit (retry will be {retry})")

        if not sender_acked:
            trace.append(f"  S ABANDON record {i} after {s.max_retries} retries")

    return {
        "trace": trace,
        "sender_delivered": s.delivered,
        "receiver_delivered": r.delivered,
        "duplicates_suppressed": r.duplicates,
        "sender_seq": s.seq,
        "receiver_expected": r.expected,
    }


def timeout_for(payload_bytes: int, bitrate: int, prop_ms: float) -> float:
    """Minimum safe stop-and-wait timeout in ms: 2*Tp + Tf + Ta + 10% margin."""
    tf_ms = (payload_bytes * 8) / bitrate * 1000.0
    ta_ms = (8 * 8) / bitrate * 1000.0  # 8-byte ACK frame
    return (2 * prop_ms + tf_ms + ta_ms) * 1.1


def utilization(payload_bytes: int, bitrate: int, prop_ms: float) -> float:
    tf_ms = (payload_bytes * 8) / bitrate * 1000.0
    return tf_ms / (tf_ms + 2 * prop_ms)


def sliding_window_util(payload_bytes: int, bitrate: int, prop_ms: float, w: int) -> float:
    tf_ms = (payload_bytes * 8) / bitrate * 1000.0
    return min(1.0, w * tf_ms / (tf_ms + 2 * prop_ms))


def main() -> None:
    print("=== Acknowledged connectionless service: stop-and-wait ARQ ===\n")

    # Frame self-check: CRC integrity
    f = Frame(TYPE_DATA, 1, b"inventory-record-0001")
    raw = f.serialize()
    assert Frame.parse(raw) is not None, "clean frame must parse"
    broken = raw[:-1] + bytes([raw[-1] ^ 0xFF])  # corrupt the crc
    assert Frame.parse(broken) is None, "corrupted frame must be discarded"
    print("Frame CRC-32 self-check passed (clean OK, corrupt discarded).\n")

    # Scenario 1: clean delivery of two records
    print("--- Scenario 1: clean channel ---")
    res = simulate([b"rec-A", b"rec-B"])
    print("\n".join(res["trace"]))
    print(f"  receiver delivered: {res['receiver_delivered']}")
    print(f"  duplicates suppressed: {res['duplicates_suppressed']}\n")

    # Scenario 2: drop the first DATA frame (retransmission on timeout)
    print("--- Scenario 2: DATA d-idx 0 dropped (timeout -> retransmit) ---")
    res = simulate([b"rec-A"], drop_data={0})
    print("\n".join(res["trace"]))
    print(f"  receiver delivered: {res['receiver_delivered']}")
    print(f"  duplicates suppressed: {res['duplicates_suppressed']}\n")

    # Scenario 3: drop the first ACK (duplicate suppressed at receiver)
    print("--- Scenario 3: ACK a-idx 0 dropped (duplicate suppressed) ---")
    res = simulate([b"rec-A"], drop_ack={0})
    print("\n".join(res["trace"]))
    print(f"  receiver delivered: {res['receiver_delivered']}")
    print(f"  duplicates suppressed: {res['duplicates_suppressed']}\n")

    # Scenario 4: the exactly-once hazard — receiver reboots after lost ACK
    print("--- Scenario 4: lost ACK + receiver reboot -> DUPLICATE DELIVERED ---")
    res = simulate([b"rec-A"], drop_ack={0}, receiver_reset_after=0)
    print("\n".join(res["trace"]))
    print(f"  receiver delivered: {res['receiver_delivered']}")
    print(f"  duplicates suppressed: {res['duplicates_suppressed']}")
    print(f"  >>> payload delivered {len(res['receiver_delivered'])} time(s) "
          "(>1 means exactly-once was violated)\n")

    # Worked numeric example: Wi-Fi link
    print("--- Worked example: 1500 B frame, 1 Mbit/s, 20 ms prop ---")
    payload = 1500
    bitrate = 1_000_000
    prop = 20.0
    tf = payload * 8 / bitrate * 1000
    print(f"  transmission time Tf    = {tf:.3f} ms")
    print(f"  minimum timeout         = {timeout_for(payload, bitrate, prop):.3f} ms")
    print(f"  stop-and-wait util  U   = {utilization(payload, bitrate, prop) * 100:.1f}%")
    print(f"  sliding-window W=8  U   = {sliding_window_util(payload, bitrate, prop, 8) * 100:.1f}%\n")

    print("Done. Each scenario above corresponds to a case in the SVG timing diagram.")


if __name__ == "__main__":
    main()
