#!/usr/bin/env python3
"""Connection-oriented vs connectionless service: classifier + demonstrations.

This stdlib-only module makes three ideas from Chapter 1 executable:

1. classify_service() encodes Tanenbaum Fig. 1-16 -- the six service classes
   you get by crossing the connection model (oriented / less) with reliability
   and whether message boundaries are preserved.
2. demonstrate_framing() shows why a *reliable byte stream* (TCP) loses the
   sender's write boundaries, and how a length prefix recovers them -- the
   same job HTTP's Content-Length header does.
3. simulate_connection() walks the six-packet client-server exchange of
   Fig. 1-18, tying each packet back to a service primitive
   (LISTEN/CONNECT/ACCEPT/SEND/RECEIVE/DISCONNECT).

No network calls, no pip dependencies. Run: python3 main.py
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import List, Optional, Tuple

# --------------------------------------------------------------------------
# 1. The six service classes (Tanenbaum Fig. 1-16)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ServiceClass:
    """One of the six standard service types."""

    name: str
    connection_oriented: bool
    reliable: bool
    keeps_boundaries: bool
    example: str
    real_protocol: str


# Order matches Fig. 1-16: connection-oriented group, then connectionless.
SERVICE_CLASSES: Tuple[ServiceClass, ...] = (
    ServiceClass("Reliable message sequence", True, True, True,
                 "Sequence of pages", "TCP+framing / SCTP"),
    ServiceClass("Reliable byte stream", True, True, False,
                 "Movie download", "TCP (RFC 9293)"),
    ServiceClass("Unreliable connection", True, False, False,
                 "Voice over IP", "RTP-style flow"),
    ServiceClass("Unreliable datagram", False, False, False,
                 "Electronic junk mail", "UDP (RFC 768)"),
    ServiceClass("Acknowledged datagram", False, True, False,
                 "Text messaging", "UDP + app ACK / CoAP"),
    ServiceClass("Request-reply", False, True, True,
                 "Database query", "DNS-over-UDP / RPC"),
)


def classify_service(
    connection_oriented: bool,
    reliable: bool,
    keeps_boundaries: bool,
) -> Optional[ServiceClass]:
    """Map (connection, reliability, boundary) requirements to a service class.

    Returns the first matching class, or None if no standard class fits the
    request-reply / acknowledged-datagram nuance exactly.
    """
    for svc in SERVICE_CLASSES:
        if (
            svc.connection_oriented == connection_oriented
            and svc.reliable == reliable
            and svc.keeps_boundaries == keeps_boundaries
        ):
            return svc
    # Fall back: pick by connection + reliability, ignoring boundaries, so the
    # caller still gets a sensible answer instead of None.
    for svc in SERVICE_CLASSES:
        if (
            svc.connection_oriented == connection_oriented
            and svc.reliable == reliable
        ):
            return svc
    return None


@dataclass(frozen=True)
class Application:
    """A workload described by its service requirements."""

    label: str
    connection_oriented: bool
    reliable: bool
    keeps_boundaries: bool


APPLICATIONS: Tuple[Application, ...] = (
    Application("DVD / movie download", True, True, False),
    Application("Book pages to typesetter", True, True, True),
    Application("Voice over IP call", True, False, False),
    Application("Spam / junk mail blast", False, False, False),
    Application("SMS with delivery receipt", False, True, False),
    Application("DNS lookup", False, True, True),
    Application("Multiplayer position updates", False, False, False),
)


# --------------------------------------------------------------------------
# 2. Byte stream vs message boundaries
# --------------------------------------------------------------------------


def naive_stream(messages: List[bytes]) -> bytes:
    """Concatenate writes the way a TCP byte stream does: boundaries vanish."""
    return b"".join(messages)


def frame_messages(messages: List[bytes]) -> bytes:
    """Prefix each message with a 4-byte big-endian length (like Content-Length)."""
    out = bytearray()
    for msg in messages:
        out += struct.pack("!I", len(msg))  # 4-byte unsigned length header
        out += msg
    return bytes(out)


def deframe_messages(stream: bytes) -> List[bytes]:
    """Recover original message boundaries from a length-prefixed stream."""
    messages: List[bytes] = []
    offset = 0
    while offset < len(stream):
        (length,) = struct.unpack_from("!I", stream, offset)
        offset += 4
        messages.append(stream[offset:offset + length])
        offset += length
    return messages


def demonstrate_framing() -> None:
    print("=" * 64)
    print("BYTE STREAM vs MESSAGE BOUNDARIES")
    print("=" * 64)
    writes = [b"A" * 1024, b"B" * 1024]
    raw = naive_stream(writes)
    print(f"App made 2 writes of 1024 bytes each.")
    print(f"  TCP byte stream delivers: 1 blob of {len(raw)} bytes "
          f"-> boundaries LOST.")
    print(f"  A reliable byte stream cannot tell 2x1024 from 1x2048.")

    framed = frame_messages(writes)
    recovered = deframe_messages(framed)
    sizes = [len(m) for m in recovered]
    print(f"  With a 4-byte length prefix ({len(framed)} bytes on wire),")
    print(f"  the receiver recovers boundaries: {sizes} -> 2 messages.")
    print()


# --------------------------------------------------------------------------
# 3. The six-packet connection-oriented exchange (Fig. 1-18)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Packet:
    seq: int
    direction: str   # "C->S" or "S->C"
    label: str
    primitive: str   # the service primitive that triggered it


def simulate_connection() -> List[Packet]:
    """Build the six-packet request-reply exchange over acknowledged datagrams.

    Server: LISTEN -> ACCEPT -> RECEIVE -> SEND -> DISCONNECT
    Client: CONNECT -> SEND -> RECEIVE -> DISCONNECT
    """
    return [
        Packet(1, "C->S", "Connect request", "CONNECT (client) / LISTEN (server)"),
        Packet(2, "S->C", "Accept response", "ACCEPT (server)"),
        Packet(3, "C->S", "Request for data", "SEND (client) -> RECEIVE (server)"),
        Packet(4, "S->C", "Reply", "SEND (server) -> RECEIVE (client)"),
        Packet(5, "C->S", "Disconnect", "DISCONNECT (client)"),
        Packet(6, "S->C", "Disconnect", "DISCONNECT (server)"),
    ]


def print_exchange(packets: List[Packet]) -> None:
    print("=" * 64)
    print("CONNECTION-ORIENTED EXCHANGE (Fig. 1-18, 6 packets)")
    print("=" * 64)
    for pkt in packets:
        arrow = "  -->  " if pkt.direction == "C->S" else "  <--  "
        left, right = ("CLIENT", "SERVER")
        body = f"({pkt.seq}) {pkt.label}"
        print(f"  {left}{arrow}{right}   {body:<22}  [{pkt.primitive}]")
    print(f"\n  Connectionless ideal would need only 2 packets (req, reply).")
    print(f"  6 are needed once messages are large, lost, or reordered:")
    print(f"  sequence numbers + ordered stream answer 'what is missing?'.")
    print()


# --------------------------------------------------------------------------
# Classification table printer
# --------------------------------------------------------------------------


def print_classification_table() -> None:
    print("=" * 64)
    print("SERVICE CLASSIFICATION (Fig. 1-16)")
    print("=" * 64)
    header = f"{'Application':<30}{'Service class':<28}{'Protocol'}"
    print(header)
    print("-" * 78)
    for app in APPLICATIONS:
        svc = classify_service(
            app.connection_oriented, app.reliable, app.keeps_boundaries
        )
        svc_name = svc.name if svc else "(no standard class)"
        proto = svc.real_protocol if svc else "-"
        print(f"{app.label:<30}{svc_name:<28}{proto}")
    print()


def spotlight() -> None:
    """The multiplayer-game failure mode from the lesson."""
    game = APPLICATIONS[-1]
    svc = classify_service(
        game.connection_oriented, game.reliable, game.keeps_boundaries
    )
    print("=" * 64)
    print("DECISION SPOTLIGHT")
    print("=" * 64)
    print(f"Workload: {game.label}")
    print("  Latest value wins; a lost update is harmless and superseded.")
    print(f"  Correct service: {svc.name if svc else '?'} "
          f"({svc.real_protocol if svc else '?'}).")
    print("  TCP here causes head-of-line blocking: one lost segment stalls")
    print("  every later byte for a full RTT. Reliability is the wrong tool.\n")


def main() -> None:
    print("\nConnection-Oriented vs Connectionless Service\n")
    print_classification_table()
    demonstrate_framing()
    print_exchange(simulate_connection())
    spotlight()


if __name__ == "__main__":
    main()
