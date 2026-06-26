"""The H.323 Protocol Stack.

A stdlib-only simulation of the H.323 call setup flow: RAS admission,
Q.931 call signaling, H.245 capability exchange, logical channel
opening, RTP media establishment, and call teardown. Includes a
comparison with the SIP protocol stack.

Run:  python3 main.py
Exit: 0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

CODECS = {
    "G.711": {"payload_type": 0, "bitrate_kbps": 64, "frame_ms": 10},
    "G.729": {"payload_type": 18, "bitrate_kbps": 8, "frame_ms": 10},
    "G.723.1": {"payload_type": 4, "bitrate_kbps": 5.3, "frame_ms": 30},
    "H.261": {"payload_type": 31, "bitrate_kbps": 64, "frame_ms": 0},
    "H.263": {"payload_type": 34, "bitrate_kbps": 64, "frame_ms": 0},
}


@dataclass
class H323Message:
    """A simulated H.323 protocol message."""
    phase: str  # "RAS", "Q.931", "H.245", "RTP"
    message_type: str
    direction: str  # "caller->callee", "callee->caller", "terminal->GK", etc.
    details: str = ""
    timestamp: float = 0.0


class Gatekeeper:
    """A simulated H.323 gatekeeper for RAS (admission control)."""

    def __init__(self) -> None:
        self.registered: Dict[str, str] = {}  # alias -> address
        self.admitted_calls: List[str] = []

    def register(self, alias: str, address: str) -> Tuple[H323Message, H323Message]:
        """Process RAS Registration Request (RRQ) -> Registration Confirm (RCF)."""
        self.registered[alias] = address
        req = H323Message("RAS", "RRQ (Registration Request)", f"{alias}->GK",
                          f"alias={alias} address={address}")
        conf = H323Message("RAS", "RCF (Registration Confirm)", f"GK->{alias}",
                           f"alias={alias} registered")
        return (req, conf)

    def admit(self, call_id: str, caller: str, callee: str) -> Tuple[H323Message, H323Message]:
        """Process RAS Admission Request (ARQ) -> Admission Confirm (ACF)."""
        self.admitted_calls.append(call_id)
        req = H323Message("RAS", "ARQ (Admission Request)", f"{caller}->GK",
                          f"call_id={call_id} dest={callee}")
        conf = H323Message("RAS", "ACF (Admission Confirm)", f"GK->{caller}",
                           f"call_id={call_id} admitted, dest_address={self.registered.get(callee, 'unknown')}")
        return (req, conf)

    def disengage(self, call_id: str) -> Tuple[H323Message, H323Message]:
        """Process RAS Disengage Request (DRQ) -> Disengage Confirm (DCF)."""
        if call_id in self.admitted_calls:
            self.admitted_calls.remove(call_id)
        req = H323Message("RAS", "DRQ (Disengage Request)", "terminal->GK", f"call_id={call_id}")
        conf = H323Message("RAS", "DCF (Disengage Confirm)", "GK->terminal", f"call_id={call_id} disengaged")
        return (req, conf)


class H323Terminal:
    """A simulated H.323 terminal (endpoint)."""

    def __init__(self, alias: str, address: str, supported_codecs: List[str]) -> None:
        self.alias = alias
        self.address = address
        self.supported_codecs = supported_codecs
        self.logical_channels: Dict[int, str] = {}  # channel_number -> media_type

    def q931_setup(self, callee: str) -> H323Message:
        """Send Q.931 SETUP message."""
        return H323Message("Q.931", "SETUP", f"{self.alias}->{callee}",
                           f"calling={self.alias} called={callee}")

    def q931_connect(self) -> H323Message:
        """Send Q.931 CONNECT message."""
        return H323Message("Q.931", "CONNECT", "callee->caller",
                           "call established, H.245 address included")

    def h245_capability_exchange(self) -> Tuple[H323Message, H323Message]:
        """H.245 capability exchange (both sides share supported codecs)."""
        req = H323Message("H.245", "TerminalCapabilitySet", f"{self.alias}->peer",
                          f"codecs={self.supported_codecs}")
        ack = H323Message("H.245", "TerminalCapabilitySetAck", "peer->" + self.alias,
                          "capabilities accepted")
        return (req, ack)

    def h245_open_logical_channel(self, channel_num: int, media_type: str, codec: str) -> H323Message:
        """Open a logical channel for media transport."""
        self.logical_channels[channel_num] = media_type
        return H323Message("H.245", "OpenLogicalChannel", f"{self.alias}->peer",
                           f"channel={channel_num} media={media_type} codec={codec}")

    def h245_close_logical_channel(self, channel_num: int) -> H323Message:
        """Close a logical channel."""
        media = self.logical_channels.pop(channel_num, "unknown")
        return H323Message("H.245", "CloseLogicalChannel", f"{self.alias}->peer",
                           f"channel={channel_num} media={media}")

    def q931_release(self) -> H323Message:
        """Send Q.931 RELEASE COMPLETE."""
        return H323Message("Q.931", "RELEASE COMPLETE", "either->either", "call released")


def main() -> None:
    print("The H.323 Protocol Stack\n")

    gk = Gatekeeper()
    caller = H323Terminal("alice@h323.example.com", "10.0.0.10:1720", ["G.711", "G.729", "H.263"])
    callee = H323Terminal("bob@h323.example.com", "10.0.0.20:1720", ["G.711", "G.723.1", "H.261"])

    trace: List[H323Message] = []

    print("=== Phase 1: RAS Registration ===\n")
    req, conf = gk.register(caller.alias, caller.address)
    trace.extend([req, conf])
    for msg in [req, conf]:
        print(f"  [{msg.phase}] {msg.direction}: {msg.message_type}")
        print(f"    {msg.details}")
    req2, conf2 = gk.register(callee.alias, callee.address)
    trace.extend([req2, conf2])
    print(f"  [{req2.phase}] {req2.direction}: {req2.message_type}")
    print(f"    {req2.details}")
    print(f"  [{conf2.phase}] {conf2.direction}: {conf2.message_type}")
    print()

    print("=== Phase 2: RAS Admission ===\n")
    arq, acf = gk.admit("call-1", caller.alias, callee.alias)
    trace.extend([arq, acf])
    for msg in [arq, acf]:
        print(f"  [{msg.phase}] {msg.direction}: {msg.message_type}")
        print(f"    {msg.details}")
    print()

    print("=== Phase 3: Q.931 Call Signaling (TCP) ===\n")
    setup = caller.q931_setup(callee.alias)
    alerting = H323Message("Q.931", "ALERTING", f"{callee.alias}->{caller.alias}", "callee is ringing")
    connect = callee.q931_connect()
    trace.extend([setup, alerting, connect])
    for msg in [setup, alerting, connect]:
        print(f"  [{msg.phase}] {msg.direction}: {msg.message_type}")
        print(f"    {msg.details}")
    print()

    print("=== Phase 4: H.245 Control Channel (TCP) ===\n")
    # Capability exchange (both directions)
    cap1, ack1 = caller.h245_capability_exchange()
    cap2, ack2 = callee.h245_capability_exchange()
    trace.extend([cap1, ack1, cap2, ack2])
    for msg in [cap1, ack1, cap2, ack2]:
        print(f"  [{msg.phase}] {msg.direction}: {msg.message_type}")
        print(f"    {msg.details}")

    # Negotiated codec: intersection of capabilities
    common_audio = set(caller.supported_codecs) & set(callee.supported_codecs) & set(CODECS.keys())
    negotiated = "G.711" if "G.711" in common_audio else next(iter(common_audio), "G.711")
    print(f"\n  Negotiated audio codec: {negotiated}")
    print()

    print("=== Phase 5: Open Logical Channels ===\n")
    olc1 = caller.h245_open_logical_channel(1, "audio", negotiated)
    olc1_ack = H323Message("H.245", "OpenLogicalChannelAck", f"{callee.alias}->{caller.alias}",
                           f"channel=1 media=audio rtp_port=5004")
    olc2 = callee.h245_open_logical_channel(2, "audio", negotiated)
    olc2_ack = H323Message("H.245", "OpenLogicalChannelAck", f"{caller.alias}->{callee.alias}",
                           f"channel=2 media=audio rtp_port=5006")
    trace.extend([olc1, olc1_ack, olc2, olc2_ack])
    for msg in [olc1, olc1_ack, olc2, olc2_ack]:
        print(f"  [{msg.phase}] {msg.direction}: {msg.message_type}")
        print(f"    {msg.details}")
    print()

    print("=== Phase 6: RTP Media Flow (UDP) ===\n")
    rtp_start = H323Message("RTP", "Media Flow", "bidirectional",
                            f"audio={negotiated} caller:5004 <-> callee:5006")
    trace.append(rtp_start)
    print(f"  [{rtp_start.phase}] {rtp_start.direction}: {rtp_start.message_type}")
    print(f"    {rtp_start.details}")
    print(f"    [Media flowing for the duration of the call]")
    print()

    print("=== Phase 7: Call Teardown ===\n")
    close1 = caller.h245_close_logical_channel(1)
    close2 = callee.h245_close_logical_channel(2)
    release = caller.q931_release()
    drq, dcf = gk.disengage("call-1")
    trace.extend([close1, close2, release, drq, dcf])
    for msg in [close1, close2, release, drq, dcf]:
        print(f"  [{msg.phase}] {msg.direction}: {msg.message_type}")
        print(f"    {msg.details}")
    print()

    print("=== H.323 Protocol Stack Summary ===\n")
    stack = [
        ("H.225 RAS", "UDP", "Registration, Admission, Status (terminal <-> gatekeeper)"),
        ("H.225 Q.931", "TCP", "Call signaling (SETUP, ALERTING, CONNECT, RELEASE)"),
        ("H.245", "TCP", "Control: capability exchange, logical channel management"),
        ("RTP", "UDP", "Media transport (audio/video)"),
        ("RTCP", "UDP", "Media quality feedback"),
    ]
    print(f"  {'Protocol':>14}  {'Transport':>9}  {'Purpose'}")
    print("  " + "-" * 60)
    for proto, transport, purpose in stack:
        print(f"  {proto:>14}  {transport:>9}  {purpose}")
    print()

    print("=== H.323 Entities ===\n")
    entities = [
        ("Terminal", "Endpoint that originates/terminates calls"),
        ("Gateway", "Connects H.323 to other networks (PSTN, SIP)"),
        ("Gatekeeper", "Address translation, admission control, bandwidth management"),
        ("MCU", "Multipoint Control Unit for multi-party conferencing"),
    ]
    for entity, desc in entities:
        print(f"  {entity:>14}: {desc}")
    print()

    print("=== H.323 vs SIP Comparison ===\n")
    comparison = [
        ("Origin", "ITU (telecom)", "IETF (Internet)"),
        ("Encoding", "ASN.1 PER (binary)", "Text (HTTP-like)"),
        ("Signaling", "Q.931 + H.245 (two channels)", "SIP (one protocol)"),
        ("Complexity", "High (multiple protocols)", "Lower (single protocol)"),
        ("Extensibility", "Hard (binary encoding)", "Easy (text headers)"),
        ("Media negotiation", "H.245 capability exchange", "SDP offer/answer"),
        ("Messages per call", "~12-15", "~6-8"),
        ("Adoption", "Legacy, declining", "Dominant in modern VoIP"),
    ]
    print(f"  {'Aspect':>18}  {'H.323':>22}  {'SIP':>22}")
    print("  " + "-" * 65)
    for aspect, h323, sip in comparison:
        print(f"  {aspect:>18}  {h323:>22}  {sip:>22}")
    print()

    print(f"Total messages in this H.323 call: {len(trace)}")
    print(f"Phases: RAS(2x) + Q.931(3) + H.245(6) + RTP(1) + Teardown(5)")
    print()

    print("Key observations:")
    print("  - H.323 uses multiple protocols across 3 phases (RAS, Q.931, H.245)")
    print("  - Q.931 and H.245 each use separate TCP connections")
    print("  - Binary ASN.1 encoding makes debugging harder than SIP's text format")
    print("  - Gatekeeper is optional but adds admission control and address translation")
    print("  - SIP's simpler design (one protocol, text encoding) led to its dominance")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
