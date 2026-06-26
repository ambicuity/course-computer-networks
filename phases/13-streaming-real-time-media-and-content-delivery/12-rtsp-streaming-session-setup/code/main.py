"""RTSP Streaming Session Setup.

A stdlib-only simulator of the RTSP (Real-Time Streaming Protocol)
session lifecycle. Implements a minimal RTSP server state machine
and client that exchanges text-based RTSP messages:

  DESCRIBE -> SETUP -> PLAY -> PAUSE -> PLAY -> TEARDOWN

Includes CSeq sequencing, Session ID tracking, Transport header
negotiation, and SDP (Session Description Protocol) generation.

Run:  python3 main.py
Exit: 0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

RTSP_VERSION = "RTSP/1.0"


@dataclass
class RTSPResponse:
    """A simulated RTSP response message."""
    status_code: int
    status_text: str
    headers: Dict[str, str] = field(default_factory=dict)
    body: str = ""

    def format(self) -> str:
        lines = [f"{RTSP_VERSION} {self.status_code} {self.status_text}"]
        for k, v in self.headers.items():
            lines.append(f"{k}: {v}")
        if self.body:
            lines.append(f"Content-Length: {len(self.body)}")
        lines.append("")
        if self.body:
            lines.append(self.body)
        return "\r\n".join(lines)


@dataclass
class RTSPRequest:
    """A simulated RTSP request message."""
    method: str
    url: str
    cseq: int
    headers: Dict[str, str] = field(default_factory=dict)

    def format(self) -> str:
        lines = [f"{self.method} {self.url} {RTSP_VERSION}"]
        lines.append(f"CSeq: {self.cseq}")
        for k, v in self.headers.items():
            lines.append(f"{k}: {v}")
        lines.append("")
        return "\r\n".join(lines)


class RTSPServer:
    """A minimal RTSP server state machine."""

    STATES = ["INIT", "READY", "PLAYING", "TEARDOWN"]

    def __init__(self, url: str) -> None:
        self.url = url
        self.state: str = "INIT"
        self.session_id: Optional[str] = None
        self.cseq_counter: int = 0
        self.client_rtp_port: int = 0
        self.server_rtp_port: int = 5004
        self.sdp: str = self._generate_sdp()
        self.tracks: Dict[int, Dict] = {}

    def _generate_sdp(self) -> str:
        return (
            "v=0\r\n"
            "o=- 2890844526 2890842807 IN IP4 192.168.1.1\r\n"
            "s=Test Stream\r\n"
            "c=IN IP4 0.0.0.0\r\n"
            "t=0 0\r\n"
            "m=video 50004 RTP/AVP 96\r\n"
            "a=rtpmap:96 H264/90000\r\n"
            "a=control:track=0\r\n"
            "m=audio 50006 RTP/AVP 0\r\n"
            "a=rtpmap:0 PCMU/8000\r\n"
            "a=control:track=1\r\n"
        )

    def handle(self, request: RTSPRequest) -> RTSPResponse:
        """Process an RTSP request and return a response, updating state."""
        method = request.method
        cseq = request.cseq

        if method == "DESCRIBE":
            return RTSPResponse(
                status_code=200,
                status_text="OK",
                headers={"CSeq": str(cseq), "Content-Type": "application/sdp"},
                body=self.sdp,
            )
        elif method == "SETUP":
            transport = request.headers.get("Transport", "")
            port = self._extract_port(transport)
            self.client_rtp_port = port
            self.session_id = f"SESSION-{cseq:06d}"
            self.state = "READY"
            resp_transport = f"RTP/AVP;unicast;client_port={port}-{port+1};server_port={self.server_rtp_port}-{self.server_rtp_port+1}"
            return RTSPResponse(
                status_code=200,
                status_text="OK",
                headers={
                    "CSeq": str(cseq),
                    "Session": self.session_id,
                    "Transport": resp_transport,
                },
            )
        elif method == "PLAY":
            if self.state not in ("READY", "PLAYING"):
                return RTSPResponse(400, "Bad Request", {"CSeq": str(cseq)})
            self.state = "PLAYING"
            range_header = request.headers.get("Range", "npt=0.000-")
            return RTSPResponse(
                status_code=200,
                status_text="OK",
                headers={
                    "CSeq": str(cseq),
                    "Session": self.session_id or "",
                    "Range": range_header,
                    "RTP-Info": "url=track=0;seq=0;rtptime=0",
                },
            )
        elif method == "PAUSE":
            if self.state != "PLAYING":
                return RTSPResponse(400, "Bad Request", {"CSeq": str(cseq)})
            self.state = "READY"
            return RTSPResponse(
                status_code=200,
                status_text="OK",
                headers={"CSeq": str(cseq), "Session": self.session_id or ""},
            )
        elif method == "TEARDOWN":
            self.state = "TEARDOWN"
            return RTSPResponse(
                status_code=200,
                status_text="OK",
                headers={"CSeq": str(cseq), "Session": self.session_id or ""},
            )
        elif method == "GET_PARAMETER":
            return RTSPResponse(
                status_code=200,
                status_text="OK",
                headers={"CSeq": str(cseq), "Session": self.session_id or ""},
            )
        else:
            return RTSPResponse(405, "Method Not Allowed", {"CSeq": str(cseq)})

    def _extract_port(self, transport: str) -> int:
        """Extract client_port from a Transport header string."""
        for part in transport.split(";"):
            part = part.strip()
            if part.startswith("client_port="):
                port_str = part.split("=")[1].split("-")[0]
                return int(port_str)
        return 50000


class RTSPClient:
    """A minimal RTSP client that sends requests and prints responses."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.cseq: int = 0
        self.session_id: Optional[str] = None
        self.server = RTSPServer(url)

    def _next_cseq(self) -> int:
        self.cseq += 1
        return self.cseq

    def _send(self, method: str, extra_headers: Optional[Dict[str, str]] = None) -> RTSPResponse:
        cseq = self._next_cseq()
        headers: Dict[str, str] = {}
        if self.session_id:
            headers["Session"] = self.session_id
        if extra_headers:
            headers.update(extra_headers)
        req = RTSPRequest(method=method, url=self.url, cseq=cseq, headers=headers)
        print(f"--- Client -> Server ---")
        print(req.format())
        resp = self.server.handle(req)
        if "Session" in resp.headers:
            self.session_id = resp.headers["Session"]
        print(f"--- Server -> Client ---")
        print(resp.format())
        print(f"[State: {self.server.state}]\n")
        return resp

    def describe(self) -> RTSPResponse:
        return self._send("DESCRIBE")

    def setup(self, track: int = 0, client_port: int = 50000) -> RTSPResponse:
        transport = f"RTP/AVP;unicast;client_port={client_port}-{client_port+1}"
        url = f"{self.url}/track={track}"
        cseq = self._next_cseq()
        req = RTSPRequest("SETUP", url, cseq, {"Transport": transport})
        print(f"--- Client -> Server ---")
        print(req.format())
        resp = self.server.handle(req)
        if "Session" in resp.headers:
            self.session_id = resp.headers["Session"]
        print(f"--- Server -> Client ---")
        print(resp.format())
        print(f"[State: {self.server.state}]\n")
        return resp

    def play(self, start: float = 0.0) -> RTSPResponse:
        return self._send("PLAY", {"Range": f"npt={start:.3f}-"})

    def pause(self) -> RTSPResponse:
        return self._send("PAUSE")

    def teardown(self) -> RTSPResponse:
        return self._send("TEARDOWN")

    def keepalive(self) -> RTSPResponse:
        return self._send("GET_PARAMETER")


def main() -> None:
    print("RTSP Streaming Session Setup\n")
    print("Simulating a complete RTSP session lifecycle:\n")

    url = "rtsp://192.168.1.1/stream"
    client = RTSPClient(url)

    print("=== Step 1: DESCRIBE (get media info as SDP) ===\n")
    client.describe()

    print("=== Step 2: SETUP (negotiate transport for video track) ===\n")
    client.setup(track=0, client_port=50000)

    print("=== Step 3: SETUP (negotiate transport for audio track) ===\n")
    client.setup(track=1, client_port=50002)

    print("=== Step 4: PLAY (start streaming from beginning) ===\n")
    client.play(start=0.0)

    print("=== Step 5: GET_PARAMETER (keepalive) ===\n")
    client.keepalive()

    print("=== Step 6: PAUSE (temporarily halt) ===\n")
    client.pause()

    print("=== Step 7: PLAY (resume from 30 seconds) ===\n")
    client.play(start=30.0)

    print("=== Step 8: TEARDOWN (end session) ===\n")
    client.teardown()

    # Summary
    print("=== Session Summary ===")
    print(f"  URL:          {url}")
    print(f"  Total CSeq:   {client.cseq}")
    print(f"  Session ID:   {client.session_id}")
    print(f"  Final state:  {client.server.state}")
    print()

    # State transition log
    print("State transitions observed:")
    transitions = [
        ("INIT", "DESCRIBE", "INIT"),
        ("INIT", "SETUP", "READY"),
        ("READY", "PLAY", "PLAYING"),
        ("PLAYING", "PAUSE", "READY"),
        ("READY", "PLAY", "PLAYING"),
        ("PLAYING", "TEARDOWN", "TEARDOWN"),
    ]
    for prev, msg, nxt in transitions:
        marker = "OK" if nxt != "TEARDOWN" or msg == "TEARDOWN" else "ERR"
        print(f"  {prev:10s} --{msg:12s}--> {nxt:10s}  [{marker}]")
    print()

    print("Key observations:")
    print("  - RTSP is text-based and stateful (like HTTP but with sessions)")
    print("  - Control runs over TCP; media flows over RTP/UDP on negotiated ports")
    print("  - CSeq matches each request to its response")
    print("  - Session ID persists across PLAY/PAUSE until TEARDOWN")
    print("  - DESCRIBE returns SDP describing codecs and tracks")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
