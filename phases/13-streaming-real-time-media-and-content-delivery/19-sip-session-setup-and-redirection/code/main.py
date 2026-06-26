"""SIP Session Setup and Redirection.

A stdlib-only SIP message parser and call-flow simulator. Parses SIP
requests and responses, models the INVITE/100/180/200/ACK/BYE state
machine, simulates registration, proxy forking, redirect responses,
and SDP offer/answer codec negotiation, and reports failure modes
(timeout, loop, codec mismatch).

Run:  python3 main.py
Exit: 0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# Common RTP payload types for the SDP offer/answer demo
RTP_PAYLOAD_TYPES: Dict[int, str] = {
    0: "PCMU/G.711u",
    8: "PCMA/G.711a",
    9: "G.722",
    18: "G.729",
}


@dataclass
class SipMessage:
    """A parsed SIP request or response."""

    is_request: bool
    method: str
    request_uri: str
    status_code: int
    reason: str
    headers: Dict[str, str]
    body: str

    @classmethod
    def parse(cls, raw: str) -> "SipMessage":
        """Parse a raw SIP message (request-line or status-line + headers + body)."""
        # Split header block from body
        if "\r\n\r\n" in raw:
            head, body = raw.split("\r\n\r\n", 1)
        elif "\n\n" in raw:
            head, body = raw.split("\n\n", 1)
        else:
            head, body = raw, ""
        lines = head.replace("\r\n", "\n").split("\n")
        start = lines[0].strip()
        headers: Dict[str, str] = {}
        for line in lines[1:]:
            if ":" in line:
                key, _, val = line.partition(":")
                headers[key.strip().lower()] = val.strip()
        # Request: METHOD sip:uri SIP/2.0 ; Response: SIP/2.0 200 OK
        if start.startswith("SIP/"):
            parts = start.split(None, 2)
            code = int(parts[1]) if len(parts) >= 2 else 0
            reason = parts[2] if len(parts) >= 3 else ""
            return cls(is_request=False, method="", request_uri="",
                       status_code=code, reason=reason,
                       headers=headers, body=body)
        parts = start.split(None, 2)
        method = parts[0] if parts else ""
        uri = parts[1] if len(parts) > 1 else ""
        return cls(is_request=True, method=method, request_uri=uri,
                   status_code=0, reason="", headers=headers, body=body)

    def summary(self) -> str:
        if self.is_request:
            return f"{self.method} {self.request_uri}"
        return f"{self.status_code} {self.reason}"


def parse_sdp_codecs(sdp: str) -> Set[int]:
    """Extract RTP payload types from an SDP m=audio line."""
    codecs: Set[int] = set()
    for line in sdp.splitlines():
        if line.startswith("m=audio"):
            # m=audio 5004 RTP/AVP 0 8 18
            tokens = line.split()
            for tok in tokens[3:]:
                try:
                    codecs.add(int(tok))
                except ValueError:
                    pass
    return codecs


def negotiate_codecs(offer: Set[int], answer: Set[int]) -> Set[int]:
    """SDP offer/answer: the intersection is the agreed codec set."""
    return offer & answer


@dataclass
class CallState:
    """High-level SIP call state machine labels."""

    state: str = "idle"
    log: List[str] = field(default_factory=list)

    def transition(self, event: str, new_state: str) -> None:
        self.log.append(f"{self.state} --{event}--> {new_state}")
        self.state = new_state


def basic_call_flow() -> CallState:
    """Simulate the INVITE/100/180/200/ACK/BYE flow."""
    cs = CallState(state="idle")
    cs.transition("INVITE sent", "calling")
    cs.transition("100 Trying", "proceeding")
    cs.transition("180 Ringing", "ringing")
    cs.transition("200 OK", "confirmed")
    cs.transition("ACK sent", "connected")
    cs.transition("BYE sent", "terminating")
    cs.transition("200 OK to BYE", "terminated")
    return cs


def fork_call_flow(contacts: List[str], answer_index: int) -> Tuple[CallState, int]:
    """Simulate forking to multiple contacts; first answer wins."""
    cs = CallState(state="idle")
    cs.transition(f"INVITE forked to {len(contacts)} contacts", "calling")
    cs.transition("100 Trying (all)", "proceeding")
    cs.transition("180 Ringing (all)", "ringing")
    winner = contacts[answer_index]
    cs.transition(f"200 OK from {winner}", "confirmed")
    # Cancel the losers
    for i, c in enumerate(contacts):
        if i != answer_index:
            cs.log.append(f"CANCEL sent to {c} (loser)")
    cs.transition("ACK sent to winner", "connected")
    cs.transition("BYE sent", "terminating")
    cs.transition("200 OK to BYE", "terminated")
    return cs, answer_index


def redirect_flow(new_contact: str) -> CallState:
    """Simulate a 302 redirect followed by a fresh INVITE."""
    cs = CallState(state="idle")
    cs.transition("INVITE sent to original", "calling")
    cs.transition("302 Moved Temporarily", "redirected")
    cs.log.append(f"Contact: {new_contact}")
    cs.transition(f"INVITE sent to {new_contact}", "calling")
    cs.transition("180 Ringing", "ringing")
    cs.transition("200 OK", "confirmed")
    cs.transition("ACK sent", "connected")
    return cs


def loop_detection_flow(own_address: str) -> Tuple[CallState, bool]:
    """Simulate loop detection via the Via header stack."""
    cs = CallState(state="idle")
    via_stack: List[str] = []
    via_stack.append("proxy-a.example.net")
    cs.transition("INVITE via proxy-a", "calling")
    via_stack.append("proxy-b.example.net")
    cs.transition("INVITE via proxy-b", "proceeding")
    # proxy-a sees its own address again
    detected = own_address in via_stack
    if detected:
        cs.transition("Via stack contains self -> 482 Loop Detected", "failed")
    return cs, detected


def main() -> None:
    print("SIP Session Setup and Redirection\n")
    print("SIP is the text-based signaling layer for VoIP. It locates the")
    print("callee, rings them, negotiates media via SDP, and tears down.\n")

    # === Part 1: Parse a SIP INVITE ===
    print("=== Part 1: Parsing a SIP INVITE ===\n")
    invite_raw = (
        "INVITE sip:bob@example.com SIP/2.0\r\n"
        "Via: SIP/2.0/UDP 192.0.2.1:5060;branch=z9hG4bK776\r\n"
        "From: <sip:alice@example.com>;tag=1928301774\r\n"
        "To: <sip:bob@example.com>\r\n"
        "Call-ID: a84b4c76@192.0.2.1\r\n"
        "CSeq: 314159 INVITE\r\n"
        "Content-Type: application/sdp\r\n"
        "Content-Length: 142\r\n"
        "\r\n"
        "v=0\r\n"
        "o=alice 12345 1 IN IP4 192.0.2.1\r\n"
        "s=-\r\n"
        "c=IN IP4 192.0.2.1\r\n"
        "t=0 0\r\n"
        "m=audio 5004 RTP/AVP 0 8\r\n"
        "a=rtpmap:0 PCMU/8000\r\n"
        "a=rtpmap:8 PCMA/8000\r\n"
    )
    msg = SipMessage.parse(invite_raw)
    print(f"  Is request: {msg.is_request}")
    print(f"  Method:    {msg.method}")
    print(f"  URI:        {msg.request_uri}")
    print(f"  From:       {msg.headers.get('from')}")
    print(f"  To:         {msg.headers.get('to')}")
    print(f"  Call-ID:    {msg.headers.get('call-id')}")
    print(f"  CSeq:       {msg.headers.get('cseq')}")
    print(f"  Summary:    {msg.summary()}")
    print()

    # === Part 2: Parse a 200 OK response ===
    print("=== Part 2: Parsing a 200 OK Response ===\n")
    ok_raw = (
        "SIP/2.0 200 OK\r\n"
        "Via: SIP/2.0/UDP 192.0.2.1:5060;branch=z9hG4bK776\r\n"
        "From: <sip:alice@example.com>;tag=1928301774\r\n"
        "To: <sip:bob@example.com>;tag=9876\r\n"
        "Call-ID: a84b4c76@192.0.2.1\r\n"
        "CSeq: 314159 INVITE\r\n"
        "Content-Type: application/sdp\r\n"
        "\r\n"
        "v=0\r\n"
        "o=bob 54321 1 IN IP4 192.0.2.2\r\n"
        "s=-\r\n"
        "c=IN IP4 192.0.2.2\r\n"
        "t=0 0\r\n"
        "m=audio 5006 RTP/AVP 8\r\n"
        "a=rtpmap:8 PCMA/8000\r\n"
    )
    resp = SipMessage.parse(ok_raw)
    print(f"  Is request:  {resp.is_request}")
    print(f"  Status code: {resp.status_code}")
    print(f"  Reason:      {resp.reason}")
    print(f"  Summary:     {resp.summary()}")
    print()

    # === Part 3: SDP codec negotiation ===
    print("=== Part 3: SDP Offer/Answer Codec Negotiation ===\n")
    offer_codecs = parse_sdp_codecs(msg.body)
    answer_codecs = parse_sdp_codecs(resp.body)
    agreed = negotiate_codecs(offer_codecs, answer_codecs)
    print(f"  Offer codecs:  {sorted(offer_codecs)} -> "
          f"{[RTP_PAYLOAD_TYPES.get(c, '?') for c in sorted(offer_codecs)]}")
    print(f"  Answer codecs: {sorted(answer_codecs)} -> "
          f"{[RTP_PAYLOAD_TYPES.get(c, '?') for c in sorted(answer_codecs)]}")
    print(f"  Agreed:        {sorted(agreed)} -> "
          f"{[RTP_PAYLOAD_TYPES.get(c, '?') for c in sorted(agreed)]}")
    print(f"  Caller port: 5004, Callee port: 5006")
    if agreed:
        print("  Result: media can flow; caller must send only the agreed payload type")
    else:
        print("  Result: 488 Not Acceptable Here (no common codec)")
    print()

    # === Part 4: Basic call flow state machine ===
    print("=== Part 4: Basic Call Flow (INVITE/100/180/200/ACK/BYE) ===\n")
    cs = basic_call_flow()
    for step in cs.log:
        print(f"  {step}")
    print()

    # === Part 5: Forking ===
    print("=== Part 5: Forking (ring desk + mobile, first answer wins) ===\n")
    contacts = ["sip:bob@desk.example.net", "sip:bob@mobile.example.net"]
    cs2, winner = fork_call_flow(contacts, answer_index=1)
    print(f"  Contacts: {contacts}")
    print(f"  Winner:   {contacts[winner]} (mobile answered first)")
    for step in cs2.log:
        print(f"  {step}")
    print()

    # === Part 6: Redirection ===
    print("=== Part 6: 302 Redirect to a New Contact ===\n")
    cs3 = redirect_flow("sip:bob@mobile.example.net")
    for step in cs3.log:
        print(f"  {step}")
    print()

    # === Part 7: Loop detection ===
    print("=== Part 7: Loop Detection via Via Header ===\n")
    cs4, looped = loop_detection_flow("proxy-a.example.net")
    print(f"  Loop detected: {looped} (482 Loop Detected)")
    for step in cs4.log:
        print(f"  {step}")
    print()

    # === Part 8: Failure modes summary ===
    print("=== Part 8: Common SIP Failure Modes ===\n")
    failures = [
        ("408 Request Timeout", "No response to INVITE; caller retransmits then gives up"),
        ("482 Loop Detected", "Proxy saw its own address in the Via stack"),
        ("486 Busy Here", "Callee is already in a call and does not support call waiting"),
        ("487 Request Terminated", "CANCEL arrived before the INVITE was answered"),
        ("488 Not Acceptable Here", "SDP offer had no codec in common with the answer"),
        ("503 Service Unavailable", "Proxy or registrar overloaded; try another host"),
        ("NAT binding expired", "Registration lapsed; inbound INVITE cannot reach the UA"),
    ]
    print(f"  {'code':>30}  {'meaning'}")
    print("  " + "-" * 70)
    for code, meaning in failures:
        print(f"  {code:>30}  {meaning}")
    print()

    print("Key observations:")
    print("  - SIP is HTTP-like text: request-line or status-line, headers, body")
    print("  - INVITE/200/ACK is a 3-way handshake because the callee generates 200 OK")
    print("  - SDP offer/answer selects codecs by intersecting payload type lists")
    print("  - A proxy forks to many contacts; first 200 OK wins, losers get CANCEL")
    print("  - A redirect server returns 302 and lets the caller re-INVITE, staying stateless")
    print("  - The Via header stack is the loop guard; seeing self means 482")
    print("  - Registration keeps the location service current; lapsed bindings cause 404")
    print()
    print("Done.")


if __name__ == "__main__":
    main()