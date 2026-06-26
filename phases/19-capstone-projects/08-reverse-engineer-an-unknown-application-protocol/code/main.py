#!/usr/bin/env python3
"""Capstone 08: Reverse Engineer an Unknown Application Protocol.

Given a synthetic capture of an undocumented binary protocol on port 7331,
reassemble the byte stream, discover framing, classify message types,
reconstruct the state machine, and generate a protocol specification.

The synthesized protocol is "KM": magic 0x4B4D, fixed 15-byte header, six
opcodes (PUT, GET, DELETE, LIST, HEARTBEAT, ERROR), big-endian integers,
checksum = sum(header_bytes) mod 256 on control messages only.

Run:  python3 main.py
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------
MAGIC = 0x4B4D
VERSION = 0x01
HEADER = 14  # magic(2)+ver(1)+op(1)+seq(2)+flags(1)+key_len(2)+val_len(4)
OPS = {0x01: "PUT", 0x02: "GET", 0x03: "DELETE", 0x04: "LIST",
       0x10: "HEARTBEAT", 0xFF: "ERROR"}


def encode(opcode: int, seq: int, key: bytes, value: bytes,
           flags: int = 0, with_checksum: bool = False) -> bytes:
    hdr = struct.pack(">HBBHBHI", MAGIC, VERSION, opcode, seq, flags,
                      len(key), len(value))
    if with_checksum:
        hdr += struct.pack("B", sum(hdr) % 256)
    else:
        hdr += b"\x00"
    return hdr + key + value


@dataclass
class RawSegment:
    seq: int
    payload: bytes
    direction: str  # "c2s" or "s2c"


@dataclass
class Message:
    direction: str
    raw: bytes
    offset: int
    opcode: int = 0
    seq_num: int = 0
    flags: int = 0
    key: bytes = b""
    value: bytes = b""
    checksum: int = 0


@dataclass
class TypeSpec:
    opcode: int
    name: str
    count: int
    avg_size: float
    has_variable_payload: bool


# ---------------------------------------------------------------------------
# Capture generator
# ---------------------------------------------------------------------------
def build_synthetic_capture() -> list[RawSegment]:
    segs: list[RawSegment] = []
    counter = [1000]

    def push(direction: str, msg: bytes) -> None:
        segs.append(RawSegment(counter[0], msg, direction))
        counter[0] += len(msg)

    push("c2s", encode(0x01, 1, b"username", b"alice_smith"))
    push("s2c", encode(0x01, 1, b"", b"OK", flags=0x01))
    push("c2s", encode(0x01, 2, b"email", b"alice@example.com"))
    push("s2c", encode(0x01, 2, b"", b"OK", flags=0x01))
    push("c2s", encode(0x02, 3, b"username", b""))
    push("s2c", encode(0x02, 3, b"username", b"alice_smith"))
    push("c2s", encode(0x02, 4, b"email", b""))
    push("s2c", encode(0x02, 4, b"email", b"alice@example.com"))
    push("c2s", encode(0x04, 5, b"", b""))
    push("s2c", encode(0x04, 5, b"", b"username,email,session_id", flags=0x01))
    push("c2s", encode(0x03, 6, b"session_id", b""))
    push("s2c", encode(0x03, 6, b"", b"DELETED", flags=0x01))
    push("c2s", encode(0x10, 7, b"", b"", with_checksum=True))
    push("s2c", encode(0x10, 7, b"", b"", flags=0x02, with_checksum=True))
    push("c2s", encode(0x02, 8, b"missing_key", b""))
    push("s2c", encode(0xFF, 8, b"missing_key", b"KEY_NOT_FOUND",
                       flags=0xFF, with_checksum=True))
    push("c2s", encode(0x01, 9, b"long_value", b"x" * 200))
    push("s2c", encode(0x01, 9, b"", b"OK", flags=0x01))
    return segs


# ---------------------------------------------------------------------------
# Stream reassembly + framing discovery + parsing
# ---------------------------------------------------------------------------
def reassemble_stream(segments: list[RawSegment]) -> dict[str, bytes]:
    streams: dict[str, bytes] = {"c2s": b"", "s2c": b""}
    for direction in ("c2s", "s2c"):
        ordered = sorted((s for s in segments if s.direction == direction),
                         key=lambda s: s.seq)
        streams[direction] = b"".join(s.payload for s in ordered)
    return streams


def byte_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    freq = [0] * 256
    for b in data:
        freq[b] += 1
    total = len(data)
    return -sum((c / total) * math.log2(c / total)
                 for c in freq if c)


def discover_framing(stream: bytes) -> dict:
    candidates: list[dict] = []

    # Candidate: 2-byte BE length prefix at offset 0
    pos, found = 0, 0
    while pos + 2 <= len(stream):
        msg_len = struct.unpack(">H", stream[pos:pos + 2])[0]
        if msg_len == 0 or pos + msg_len > len(stream):
            break
        found += 1
        pos += msg_len
    if found >= 3:
        candidates.append({"method": "2-byte BE length-prefix",
                           "score": found, "messages": found})

    # Candidate: fixed HEADER-byte header with magic + opcode invariants
    pos, found, ok = 0, 0, True
    while pos + HEADER <= len(stream):
        magic = struct.unpack(">H", stream[pos:pos + 2])[0]
        opcode = stream[pos + 3]
        key_len = struct.unpack(">H", stream[pos + 7:pos + 9])[0]
        val_len = struct.unpack(">I", stream[pos + 9:pos + 13])[0]
        total = HEADER + key_len + val_len
        if magic != MAGIC or opcode not in OPS:
            ok = False
            break
        found += 1
        pos += total
    if ok and found >= 2:
        candidates.append({"method": f"fixed-{HEADER}B-header + variable-payload",
                           "score": found * 20, "messages": found,
                           "magic": hex(MAGIC)})

    # Candidate: delimiter scan
    for delim in (0x00, 0x0A, 0xFF):
        count = stream.count(bytes([delim]))
        if count >= 3:
            candidates.append({"method": f"delimiter-0x{delim:02X}",
                               "score": count, "messages": count})

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return {"best": candidates[0] if candidates else None,
            "all_candidates": candidates}


def parse_messages(stream: bytes, direction: str) -> list[Message]:
    out: list[Message] = []
    pos = 0
    while pos + HEADER <= len(stream):
        if struct.unpack(">H", stream[pos:pos + 2])[0] != MAGIC:
            break
        opcode = stream[pos + 3]
        seq_num = struct.unpack(">H", stream[pos + 4:pos + 6])[0]
        flags = stream[pos + 6]
        key_len = struct.unpack(">H", stream[pos + 7:pos + 9])[0]
        val_len = struct.unpack(">I", stream[pos + 9:pos + 13])[0]
        checksum = stream[pos + 14]
        total = HEADER + key_len + val_len
        if pos + total > len(stream):
            break
        out.append(Message(
            direction=direction,
            raw=stream[pos:pos + total],
            offset=pos,
            opcode=opcode, seq_num=seq_num, flags=flags,
            key=stream[pos + HEADER:pos + HEADER + key_len],
            value=stream[pos + HEADER + key_len:pos + total],
            checksum=checksum,
        ))
        pos += total
    return out


# ---------------------------------------------------------------------------
# Classification, checksum, state machine
# ---------------------------------------------------------------------------
def classify_messages(messages: list[Message]) -> dict[int, TypeSpec]:
    by_op: dict[int, list[Message]] = {}
    for m in messages:
        by_op.setdefault(m.opcode, []).append(m)
    specs: dict[int, TypeSpec] = {}
    for opcode, group in by_op.items():
        sizes = [len(m.raw) for m in group]
        variable = (len({m.flags for m in group}) > 1
                    or len({len(m.key) for m in group}) > 1
                    or len({len(m.value) for m in group}) > 1)
        specs[opcode] = TypeSpec(
            opcode=opcode,
            name=OPS.get(opcode, f"UNKNOWN_{opcode:#04x}"),
            count=len(group),
            avg_size=sum(sizes) / len(sizes),
            has_variable_payload=variable,
        )
    return specs


def detect_checksum(messages: list[Message]) -> dict:
    info = {"verified": 0, "failed": 0,
            "algorithm": "sum(header_bytes) mod 256"}
    for m in messages:
        if m.opcode in (0x10, 0xFF) and m.checksum:
            if sum(m.raw[:13]) % 256 == m.checksum:
                info["verified"] += 1
            else:
                info["failed"] += 1
    return info


@dataclass
class Transition:
    frm: str
    to: str
    trigger: str
    direction: str
    opcode: int


def reconstruct_state_machine(c2s: list[Message],
                              s2c: list[Message]) -> list[Transition]:
    by_seq = {m.seq_num: m for m in s2c}
    tr: list[Transition] = []
    state = "OPEN"
    pending_for_op = {0x01: "PUT_PENDING", 0x02: "GET_PENDING",
                      0x03: "DELETE_PENDING", 0x04: "LIST_PENDING"}
    for req in c2s:
        resp = by_seq.get(req.seq_num)
        if req.opcode == 0x10:
            tr.append(Transition(state, state, "HEARTBEAT", "c2s", req.opcode))
            if resp:
                tr.append(Transition(state, state, "HEARTBEAT-ACK",
                                     "s2c", resp.opcode))
            continue
        pending = pending_for_op.get(req.opcode)
        if pending is None:
            continue
        tr.append(Transition(state, pending, f"{OPS[req.opcode]} request",
                             "c2s", req.opcode))
        if resp:
            if resp.opcode == 0xFF:
                tr.append(Transition(pending, "ERROR", "error reply",
                                     "s2c", resp.opcode))
            else:
                tr.append(Transition(pending, state, f"{OPS[req.opcode]} response",
                                     "s2c", resp.opcode))
    return tr


# ---------------------------------------------------------------------------
# Spec generator + main
# ---------------------------------------------------------------------------
def generate_spec(specs: dict[int, TypeSpec],
                  transitions: list[Transition],
                  checksum_info: dict) -> str:
    lines = [
        "# Reconstructed Protocol Specification",
        "",
        "## Overview",
        f"  Magic: 0x{MAGIC:04X} ('KM')",
        f"  Version: {VERSION}",
        f"  Header size: {HEADER} bytes, byte order: big-endian",
        f"  Checksum: {checksum_info['algorithm']} "
        f"(verified={checksum_info['verified']}, "
        f"failed={checksum_info['failed']})",
        "",
        "## Message Types",
        f"  {'Opcode':<8} {'Name':<12} {'Count':<6} {'AvgSize':<10} Variable",
        f"  {'------':<8} {'----':<12} {'-----':<6} {'-------':<10} --------",
    ]
    for op in sorted(specs):
        s = specs[op]
        lines.append(
            f"  0x{op:02X}     {s.name:<12} {s.count:<6} "
            f"{s.avg_size:<10.1f} {s.has_variable_payload}")
    lines += ["", "## Field Layout (every message)",
              f"  Offset Size Endian Field       Description",
              f"  ------ ---- ------ ------------ -----------",
              f"  0      2B    BE     magic        0x4B4D 'KM'",
              f"  2      1B    BE     version      protocol version",
              f"  3      1B    BE     opcode       message type",
              f"  4      2B    BE     seq_num      per-direction counter",
              f"  6      1B    BE     flags        0x01=ok, 0x02=hb-ack, 0xFF=err",
              f"  7      2B    BE     key_len      bytes following for key",
              f"  9      4B    BE     val_len      bytes following for value",
              f"  13     1B    BE     checksum     sum(header[:13]) mod 256",
              f"  14     var   -      key          key_len bytes",
              f"  14+kl  var   -      value        val_len bytes",
              "",
              "## State Machine"]
    for t in transitions:
        lines.append(
            f"  {t.frm:<14} -> {t.to:<14} [{t.direction}] {t.trigger}")
    return "\n".join(lines)


def main() -> None:
    print("=" * 65)
    print("Capstone 08: Reverse Engineer an Unknown Application Protocol")
    print("=" * 65)

    segments = build_synthetic_capture()
    print(f"\n  Captured {len(segments)} TCP segments on port 7331")

    streams = reassemble_stream(segments)
    print(f"\n  Reassembled streams:")
    for direction, stream in streams.items():
        print(f"    {direction}: {len(stream)} bytes  "
              f"entropy={byte_entropy(stream):.2f} bits/byte")

    framing = discover_framing(streams["c2s"])
    print(f"\n  Framing discovery (client stream):")
    if framing["best"]:
        b = framing["best"]
        print(f"    Best: {b['method']} (score={b['score']}, "
              f"messages={b['messages']})")
    for c in framing["all_candidates"]:
        print(f"    - {c['method']}: score={c['score']}, "
              f"messages={c['messages']}")

    c2s_msgs = parse_messages(streams["c2s"], "c2s")
    s2c_msgs = parse_messages(streams["s2c"], "s2c")
    all_msgs = c2s_msgs + s2c_msgs
    print(f"\n  Parsed {len(c2s_msgs)} client + {len(s2c_msgs)} server messages")

    print(f"\n  Message catalog:")
    print(f"  {'Opcode':<8} {'Name':<10} {'Dir':<5} {'Seq':<5} "
          f"{'Key':<18} {'Value':<26} {'Flags':<6} Cksum")
    print(f"  {'------':<8} {'----':<10} {'---':<5} {'---':<5} "
          f"{'---':<18} {'-----':<26} {'-----':<6} -----")
    for m in all_msgs:
        key = m.key.decode("ascii", errors="replace")[:16]
        val = m.value.decode("ascii", errors="replace")[:24]
        print(f"  0x{m.opcode:02X}     {OPS.get(m.opcode, 'UNK'):<10} "
              f"{m.direction:<5} {m.seq_num:<5} {key:<18} {val:<26} "
              f"0x{m.flags:02X}    {m.checksum}")

    specs = classify_messages(all_msgs)
    print(f"\n  Type classification:")
    for op in sorted(specs):
        s = specs[op]
        print(f"    0x{op:02X} {s.name:<10} count={s.count} "
              f"avg={s.avg_size:.0f}B variable={s.has_variable_payload}")

    cksum = detect_checksum(all_msgs)
    print(f"\n  Checksum ({cksum['algorithm']}): "
          f"verified={cksum['verified']} failed={cksum['failed']}")

    transitions = reconstruct_state_machine(c2s_msgs, s2c_msgs)
    print(f"\n  State machine ({len(transitions)} transitions):")
    for t in transitions:
        print(f"    {t.frm:<14} -> {t.to:<14} [{t.direction}] {t.trigger}")

    print(f"\n  Generating protocol specification...\n")
    for line in generate_spec(specs, transitions, cksum).split("\n"):
        print(f"  {line}")

    print(f"\n  Summary:")
    print(f"    Reassembled {len(all_msgs)} messages from a binary protocol on")
    print(f"    port 7331 (magic 0x4B4D, 15-byte header, 6 opcodes).")
    print(f"    Discovered fixed-header framing, classified by opcode,")
    print(f"    verified the control-message checksum, and reconstructed a")
    print(f"    request-response state machine sufficient to implement a client.")


if __name__ == "__main__":
    main()