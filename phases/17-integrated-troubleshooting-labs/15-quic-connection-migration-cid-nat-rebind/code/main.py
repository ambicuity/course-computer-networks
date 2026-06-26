#!/usr/bin/env python3
"""QUIC Connection Migration and CID under NAT rebinding.

Reference oracle for the integrated troubleshooting lab. Walks the
QUIC path-validation state machine (RFC 9000 sec. 8.2) and the
spare-CID budget that determines whether a migration can succeed.

Scenarios:

  1) spare_cid_exhausted
     Server has active_connection_id_limit=2. After the Wi-Fi path
     drops, the server has no spare CID to address the LTE path.
     PATH_CHALLENGE is never sent; the new path never validates.

  2) path_response_lost
     Server has limit=8 (spares available), PATH_CHALLENGE is sent,
     but the response is dropped by a CGN. Path validation times
     out at 3*pto and the connection closes with 0x0c.

  3) happy_path
     Limit=8, challenge and response both delivered, path moves
     to Validated, migration succeeds, no CONNECTION_CLOSE.

Run:  python3 main.py --scenario spare_cid_exhausted
      python3 main.py --scenario path_response_lost
      python3 main.py --scenario happy_path
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from enum import Enum


class PathState(str, Enum):
    """RFC 9000 sec. 8.2 path-validation states."""

    UNKNOWN = "Unknown"
    VALIDATING = "Validating"
    VALIDATED = "Validated"
    FAILED = "Failed"


class FrameType(str, Enum):
    """Subset of QUIC frame types relevant to migration."""

    PATH_CHALLENGE = "PATH_CHALLENGE"
    PATH_RESPONSE = "PATH_RESPONSE"
    NEW_CONNECTION_ID = "NEW_CONNECTION_ID"
    RETIRE_CONNECTION_ID = "RETIRE_CONNECTION_ID"
    CONNECTION_CLOSE = "CONNECTION_CLOSE"


class ErrorCode(int, Enum):
    """QUIC transport error codes (RFC 9000 sec. 22)."""

    NO_ERROR = 0x00
    PATH_RESPONSE_ERROR = 0x0C


@dataclass(frozen=True)
class Frame:
    """A single QUIC frame recorded for the trace."""

    t_seconds: float
    kind: FrameType
    note: str


@dataclass
class Server:
    """The server-side view: a CID pool and an active path state."""

    cid_limit: int
    issued: list[int] = field(default_factory=list)
    retired: list[int] = field(default_factory=list)
    spares: int = 0
    active_path: PathState = PathState.UNKNOWN

    def issue(self, seq: int) -> bool:
        """Try to issue a new CID. Returns False if at the cap."""
        if len(self.issued) - len(self.retired) >= self.cid_limit:
            return False
        self.issued.append(seq)
        self.spares = self.cid_limit - (len(self.issued) - len(self.retired))
        return True

    def retire(self, seq: int) -> None:
        if seq in self.issued and seq not in self.retired:
            self.retired.append(seq)
        self.spares = self.cid_limit - (len(self.issued) - len(self.retired))


def simulate(scenario: str) -> tuple[list[Frame], list[str]]:
    """Run a scenario and return its event trace plus verdict lines."""
    events: list[Frame] = []
    verdict: list[str] = []
    t = 0.0

    if scenario == "happy_path":
        srv = Server(cid_limit=8)
        t += 0.001
        srv.issue(0)
        srv.issue(1)
        events.append(Frame(t, FrameType.NEW_CONNECTION_ID, "seq=0, retire_prior_to=0"))
        events.append(Frame(t, FrameType.NEW_CONNECTION_ID, "seq=1, retire_prior_to=0"))
        t += 0.060
        srv.active_path = PathState.VALIDATING
        events.append(Frame(t, FrameType.PATH_CHALLENGE, "token=a3:1b:00:01:02:03:04:05"))
        t += 0.018
        events.append(Frame(t, FrameType.PATH_RESPONSE, "token=a3:1b:00:01:02:03:04:05 echoed"))
        srv.active_path = PathState.VALIDATED
        verdict.append("Path transitioned Unknown -> Validating -> Validated.")
        verdict.append("Connection survives the Wi-Fi to LTE roam; no CONNECTION_CLOSE.")

    elif scenario == "spare_cid_exhausted":
        srv = Server(cid_limit=2)
        t += 0.001
        srv.issue(0)
        srv.issue(1)
        events.append(Frame(t, FrameType.NEW_CONNECTION_ID, "seq=0"))
        events.append(Frame(t, FrameType.NEW_CONNECTION_ID, "seq=1"))
        t += 120.000
        events.append(Frame(t, FrameType.RETIRE_CONNECTION_ID, "seq=0 (Wi-Fi path down)"))
        srv.retire(0)
        verdict.append(
            f"Spare-CID budget = {srv.spares}. Server has 1 spare; cannot issue "
            "a fresh CID for the LTE path because CID 1 is bound to the Wi-Fi "
            "four-tuple."
        )
        t += 8.411
        verdict.append("PATH_CHALLENGE is not emitted; server cannot address new path.")
        t += 0.0
        events.append(
            Frame(t + 131.711, FrameType.CONNECTION_CLOSE,
                  f"error_code=0x{ErrorCode.PATH_RESPONSE_ERROR.value:02x} reason='path validation failed'")
        )
        srv.active_path = PathState.FAILED
        verdict.append("Connection closes with PATH_RESPONSE_ERROR (0x0c) at the validation timeout.")

    elif scenario == "path_response_lost":
        srv = Server(cid_limit=8)
        t += 0.001
        for s in (0, 1, 2, 3):
            srv.issue(s)
            events.append(Frame(t, FrameType.NEW_CONNECTION_ID, f"seq={s}"))
        t += 128.411
        srv.active_path = PathState.VALIDATING
        events.append(Frame(t, FrameType.PATH_CHALLENGE, "token=5d:7e:11:22:33:44:55:66"))
        verdict.append("PATH_RESPONSE expected by t=128.601 (RTT 190ms). CGN drops inbound UDP/443.")
        verdict.append("3*pto = 1.5s elapses with no PATH_RESPONSE.")
        events.append(
            Frame(t + 3.879, FrameType.CONNECTION_CLOSE,
                  f"error_code=0x{ErrorCode.PATH_RESPONSE_ERROR.value:02x} reason='path validation failed'")
        )
        srv.active_path = PathState.FAILED
        verdict.append("Path transitions to Failed; connection closes with 0x0c.")

    else:
        verdict.append(f"Unknown scenario: {scenario}")

    return events, verdict


def render(events: list[Frame], verdict: list[str], scenario: str) -> str:
    out: list[str] = []
    out.append("=" * 64)
    out.append(f"QUIC MIGRATION ORACLE  --  scenario: {scenario}")
    out.append("=" * 64)
    out.append("")
    out.append(f"{'t (s)':>8}  {'frame':<22}  note")
    out.append("-" * 64)
    for e in events:
        out.append(f"{e.t_seconds:>8.3f}  {e.kind.value:<22}  {e.note}")
    out.append("")
    out.append("Verdict:")
    for line in verdict:
        out.append(f"  - {line}")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--scenario",
        choices=("spare_cid_exhausted", "path_response_lost", "happy_path"),
        default="spare_cid_exhausted",
    )
    args = parser.parse_args()
    events, verdict = simulate(args.scenario)
    print(render(events, verdict, args.scenario))


if __name__ == "__main__":
    main()
