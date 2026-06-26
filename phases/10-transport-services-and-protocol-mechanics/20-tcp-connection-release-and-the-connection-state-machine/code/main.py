#!/usr/bin/env python3
"""TCP connection-release finite state machine simulator.

Walks the 11-state FSM (RFC 793 Figure 6-39) through the three close
variants -- normal active close, simultaneous close, and abortive
close -- and prints the segment timeline and TIME_WAIT countdown for
each.

No network calls, no third-party packages -- pure stdlib so it runs
anywhere with `python3 main.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class State(str, Enum):
    CLOSED = "CLOSED"
    LISTEN = "LISTEN"
    SYN_SENT = "SYN_SENT"
    SYN_RCVD = "SYN_RCVD"
    ESTABLISHED = "ESTABLISHED"
    FIN_WAIT_1 = "FIN_WAIT_1"
    FIN_WAIT_2 = "FIN_WAIT_2"
    CLOSE_WAIT = "CLOSE_WAIT"
    CLOSING = "CLOSING"
    LAST_ACK = "LAST_ACK"
    TIME_WAIT = "TIME_WAIT"


class Event(str, Enum):
    APP_CONNECT = "app/CONNECT"
    APP_LISTEN = "app/LISTEN"
    APP_CLOSE = "app/CLOSE"
    SEG_SYN = "seg/SYN"
    SEG_SYN_ACK = "seg/SYN+ACK"
    SEG_ACK = "seg/ACK"
    SEG_FIN = "seg/FIN"
    SEG_FIN_ACK = "seg/FIN+ACK"
    SEG_RST = "seg/RST"
    TIMEOUT_2MSL = "timeout/2*MSL"


DEFAULT_MSL_SEC = 60.0


@dataclass(frozen=True)
class Transition:
    state: State
    event: Event
    next_state: State
    action: str


TRANSITIONS: list[Transition] = [
    Transition(State.CLOSED, Event.APP_CONNECT, State.SYN_SENT, "send SYN"),
    Transition(State.CLOSED, Event.APP_LISTEN, State.LISTEN, "-"),
    Transition(State.LISTEN, Event.SEG_SYN, State.SYN_RCVD, "send SYN+ACK"),
    Transition(State.SYN_SENT, Event.SEG_SYN_ACK, State.ESTABLISHED, "send ACK"),
    Transition(State.SYN_SENT, Event.SEG_SYN, State.SYN_RCVD, "send SYN+ACK (simultaneous open)"),
    Transition(State.SYN_RCVD, Event.SEG_ACK, State.ESTABLISHED, "-"),
    Transition(State.ESTABLISHED, Event.APP_CLOSE, State.FIN_WAIT_1, "send FIN"),
    Transition(State.ESTABLISHED, Event.SEG_FIN, State.CLOSE_WAIT, "send ACK"),
    Transition(State.FIN_WAIT_1, Event.SEG_ACK, State.FIN_WAIT_2, "-"),
    Transition(State.FIN_WAIT_1, Event.SEG_FIN, State.CLOSING, "send ACK"),
    Transition(State.FIN_WAIT_2, Event.SEG_FIN, State.TIME_WAIT, "send ACK"),
    Transition(State.CLOSING, Event.SEG_ACK, State.TIME_WAIT, "-"),
    Transition(State.CLOSE_WAIT, Event.APP_CLOSE, State.LAST_ACK, "send FIN"),
    Transition(State.LAST_ACK, Event.SEG_ACK, State.CLOSED, "-"),
    Transition(State.TIME_WAIT, Event.TIMEOUT_2MSL, State.CLOSED, "-"),
    Transition(State.ESTABLISHED, Event.SEG_RST, State.CLOSED, "- (abortive)"),
    Transition(State.LISTEN, Event.SEG_RST, State.LISTEN, "- (ignored)"),
]


def lookup(state: State, event: Event) -> Transition | None:
    for tr in TRANSITIONS:
        if tr.state == state and tr.event == event:
            return tr
    return None


@dataclass
class Side:
    """One side of a TCP connection and the trace of states it visits."""

    name: str
    state: State = State.CLOSED
    history: list[tuple[State, Event | None, str]] = field(default_factory=list)

    def apply(self, event: Event) -> Transition | None:
        tr = lookup(self.state, event)
        if tr is None:
            self.history.append((self.state, event, "REJECTED (illegal)"))
            return None
        self.history.append((self.state, event, f"action: {tr.action} -> {tr.next_state.value}"))
        self.state = tr.next_state
        return tr


def run_script(side_name: str, events: list[Event]) -> Side:
    side = Side(name=side_name)
    side.history.append((State.CLOSED, None, "initial"))
    for event in events:
        side.apply(event)
    return side


def active_close() -> tuple[Side, Side]:
    """Normal active close: client sends first FIN, server is passive."""
    client = run_script("client", [
        Event.APP_CONNECT,
        Event.SEG_SYN_ACK,
        Event.APP_CLOSE,
        Event.SEG_ACK,
        Event.SEG_FIN,
        Event.TIMEOUT_2MSL,
    ])
    server = run_script("server", [
        Event.APP_LISTEN,
        Event.SEG_SYN,
        Event.SEG_ACK,
        Event.SEG_FIN,
        Event.SEG_ACK,
    ])
    return client, server


def simultaneous_close() -> tuple[Side, Side]:
    """Both sides send FIN before receiving the peer's FIN."""
    a = run_script("A", [
        Event.APP_CONNECT, Event.SEG_SYN_ACK, Event.APP_CLOSE,
        Event.SEG_FIN, Event.SEG_ACK, Event.TIMEOUT_2MSL,
    ])
    b = run_script("B", [
        Event.APP_LISTEN, Event.SEG_SYN, Event.SEG_ACK, Event.APP_CLOSE,
        Event.SEG_FIN, Event.SEG_ACK, Event.TIMEOUT_2MSL,
    ])
    return a, b


def abortive_close() -> tuple[Side, Side]:
    """One side sends RST; the connection drops with no TIME_WAIT."""
    client = run_script("client", [
        Event.APP_CONNECT, Event.SEG_SYN_ACK, Event.SEG_RST,
    ])
    server = run_script("server", [
        Event.APP_LISTEN, Event.SEG_SYN, Event.SEG_ACK, Event.SEG_RST,
    ])
    return client, server


def time_wait_duration_msl(msl: float = DEFAULT_MSL_SEC) -> float:
    return 2.0 * msl


def show_trace(side: Side) -> None:
    print(f"\n  {side.name}: final state = {side.state.value}")
    for state, event, note in side.history:
        ev = event.value if event else "init"
        print(f"    {state.value:<11} | {ev:<14} | {note}")


def show_segments(variant: str) -> None:
    segments = {
        "Normal active close (4 segments without piggyback, 3 with)": [
            ("client -> server", "FIN  seq=u"),
            ("server -> client", "ACK  ack=u+1"),
            ("server -> client", "FIN  seq=v  (often piggybacked on the ACK above)"),
            ("client -> server", "ACK  ack=v+1  (then TIME_WAIT 2*MSL)"),
        ],
        "Simultaneous close (4 segments)": [
            ("A -> B", "FIN seq=u"),
            ("B -> A", "FIN seq=v"),
            ("A -> B", "ACK ack=v+1"),
            ("B -> A", "ACK ack=u+1  (both enter TIME_WAIT)"),
        ],
        "Abortive close (1 segment)": [
            ("any -> peer", "RST"),
            ("peer", "drops connection, no TIME_WAIT"),
        ],
    }
    print(f"\n  {variant}:")
    for arrow, desc in segments[variant]:
        print(f"    {arrow:<18} {desc}")


def main() -> None:
    print("=" * 70)
    print("TCP CONNECTION RELEASE  --  11-state FSM, TIME_WAIT, and the close variants")
    print("=" * 70)

    print(f"\nDefault MSL = {DEFAULT_MSL_SEC:.0f}s  =>  TIME_WAIT = {time_wait_duration_msl():.0f}s")
    print("Reason: (1) let delayed duplicates die; (2) absorb lost final ACK.")

    print("\n[1] Normal active close (client initiates):")
    client, server = active_close()
    show_trace(client)
    show_trace(server)
    show_segments("Normal active close (4 segments without piggyback, 3 with)")

    print("\n[2] Simultaneous close (both sides send FIN):")
    a, b = simultaneous_close()
    show_trace(a)
    show_trace(b)
    show_segments("Simultaneous close (4 segments)")

    print("\n[3] Abortive close (RST, no TIME_WAIT):")
    client, server = abortive_close()
    show_trace(client)
    show_trace(server)
    show_segments("Abortive close (1 segment)")

    print("\n[4] Illegal transition check:")
    bad = Side(name="attacker")
    bad.history.append((State.LISTEN, None, "initial"))
    result = bad.apply(Event.SEG_FIN)
    show_trace(bad)
    if result is None:
        print("   -> the FSM correctly rejected a FIN from LISTEN.")

    print("\nDone. Run `ss -tn state time-wait` to see TIME_WAIT sockets on this host.")


if __name__ == "__main__":
    main()