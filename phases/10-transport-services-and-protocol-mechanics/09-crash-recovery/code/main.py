"""Crash Recovery in Reliable Transport Protocols (RFC 793, 1122, 5482).

A stdlib-only toolkit that exercises the seven crash-recovery cases from
Tanenbaum & Wetherall, the Two-Army impossibility result, the Fig 6-18
strategy matrix, and a small sender-side state machine that processes
CRASH / RESTART / TIMEOUT / ACK events.

Run: python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


# --- Seven-case taxonomy (Tanenbaum & Wetherall, Computer Networks 5e, 6.6) -
SENDER = "sender"
RECEIVER = "receiver"
CLIENT = "client"
SERVER = "server"
BOTH = "both"


@dataclass(frozen=True)
class CrashCase:
    number: int
    last_sender: str
    victim: str
    survivor_dilemma: str
    recommended_action: str


SEVEN_CASES: dict[tuple[str, str], CrashCase] = {
    (CLIENT, SERVER): CrashCase(
        1, CLIENT, SERVER,
        "server lost unacked sent-data state",
        "RST by recovered server; client retransmits on next push",
    ),
    (SERVER, SERVER): CrashCase(
        2, SERVER, SERVER,
        "server's last segments may already be in the client buffer",
        "seq# discards duplicates; retransmission is idempotent",
    ),
    (CLIENT, CLIENT): CrashCase(
        3, CLIENT, CLIENT,
        "server still open, client lost its control block",
        "server keep-alive or user-timeout; client reopens",
    ),
    (SERVER, CLIENT): CrashCase(
        4, SERVER, CLIENT,
        "server mid-send, client's TCP state is gone",
        "RTO retransmits; client tears down on RST",
    ),
    (CLIENT, SERVER): CrashCase(
        5, CLIENT, SERVER,
        "server may have delivered bytes to its application",
        "application idempotency + write-ahead log required",
    ),
    (SERVER, SERVER): CrashCase(
        6, SERVER, SERVER,
        "server is the last sender AND the crash victim",
        "recovered server retransmits; seq# discards dupes",
    ),
    (BOTH, BOTH): CrashCase(
        7, BOTH, BOTH,
        "both endpoints lost their control blocks",
        "app-level checkpoint + cold restart from durable offset",
    ),
}


def classify_crash(last_sender: str, victim: str) -> CrashCase:
    """Return the seven-case classification for a (last_sender, victim) pair."""
    if last_sender == victim == BOTH:
        return SEVEN_CASES[(BOTH, BOTH)]
    if (last_sender, victim) not in SEVEN_CASES:
        raise ValueError(f"unknown shape: last_sender={last_sender} victim={victim}")
    return SEVEN_CASES[(last_sender, victim)]


# --- Fig 6-18 strategy matrix (Tanenbaum) --------------------------------------
class ServerStrategy(Enum):
    ACK_FIRST = "ack_then_write"
    WRITE_FIRST = "write_then_ack"


class ClientStrategy(Enum):
    ALWAYS = "always_retransmit"
    NEVER = "never_retransmit"
    S0 = "retransmit_if_no_outstanding"
    S1 = "retransmit_if_outstanding"


def fig_618_outcome(server: ServerStrategy, client: ClientStrategy,
                    crash_after_ack: bool, crash_after_write: bool) -> str:
    """Compute OK / DUP / LOST for one (server, client, crash_point) tuple.

    The classic impossibility result: no client strategy dominates for every
    crash point under a given server strategy.
    """
    if not crash_after_ack and not crash_after_write:
        return "OK"
    if crash_after_ack and not crash_after_write:
        if server == ServerStrategy.ACK_FIRST:
            app_has, out = True, False
        else:
            app_has, out = False, True
    elif not crash_after_ack and crash_after_write:
        if server == ServerStrategy.ACK_FIRST:
            app_has, out = True, False
        else:
            app_has, out = True, True
    else:
        if server == ServerStrategy.ACK_FIRST:
            app_has, out = True, False
        else:
            app_has, out = True, True

    if client == ClientStrategy.ALWAYS:
        will = True
    elif client == ClientStrategy.NEVER:
        will = False
    elif client == ClientStrategy.S0:
        will = not out
    else:
        will = out

    if will and app_has:
        return "DUP"
    if not will and not app_has:
        return "LOST"
    return "OK"


# --- Two-Army Problem: exhaustion argument ------------------------------------
def two_army_worst_case_messages(k_rounds: int) -> int:
    """Distinct message kinds a k-round protocol needs to settle the question.

    Round 1 introduces 2 messages (M1, ACK1); each subsequent round adds 2.
    The last one is still unconfirmed, which is the impossibility result.
    """
    if k_rounds < 1:
        return 0
    return 2 * k_rounds + 1


# --- Sender-side state machine ------------------------------------------------
class S(Enum):
    IDLE = auto()
    OPENED = auto()
    SENT_X = auto()
    DELIVERED = auto()
    DOWN = auto()
    RST_SENT = auto()


class Evt(Enum):
    OPEN = auto()
    SEND = auto()
    ACK = auto()
    CRASH = auto()
    RESTART = auto()
    TIMEOUT = auto()


@dataclass
class TransferFSM:
    user_timeout_seconds: float = 5.0
    state: S = S.IDLE
    unacked_byte_range: Optional[tuple[int, int]] = None
    trace: list[tuple[S, Evt, S, str]] = field(default_factory=list)

    def step(self, evt: Evt) -> S:
        prev = self.state
        nxt, note = self._transition(prev, evt)
        self.trace.append((prev, evt, nxt, note))
        self.state = nxt
        return nxt

    def _transition(self, prev: S, evt: Evt) -> tuple[S, str]:
        if evt == Evt.CRASH and prev in (S.OPENED, S.SENT_X, S.DELIVERED):
            return S.DOWN, f"peer crash; arming user-timeout={self.user_timeout_seconds}s"
        if evt == Evt.RESTART and prev == S.DOWN:
            return S.OPENED, "recovered; unacked range lost unless WAL'd"
        if evt == Evt.TIMEOUT and prev in (S.OPENED, S.SENT_X, S.DOWN):
            return S.RST_SENT, "user-timeout fired; emit RST"
        if prev == S.IDLE and evt == Evt.OPEN:
            return S.OPENED, "3-way handshake complete"
        if prev == S.OPENED and evt == Evt.SEND:
            self.unacked_byte_range = (100, 200)
            return S.SENT_X, f"sent bytes {self.unacked_byte_range}"
        if prev == S.SENT_X and evt == Evt.ACK:
            self.unacked_byte_range = None
            return S.DELIVERED, "ack received; range durable"
        return prev, f"event {evt.name} ignored in {prev.name}"


# --- Demo ---------------------------------------------------------------------
def demo_seven_cases() -> None:
    print("=" * 70)
    print("CRASH RECOVERY - SEVEN CASES (Tanenbaum & Wetherall 5e, 6.6)")
    print("=" * 70)
    for last, victim in [(CLIENT, SERVER), (SERVER, SERVER),
                         (CLIENT, CLIENT), (SERVER, CLIENT),
                         (CLIENT, SERVER), (SERVER, SERVER),
                         (BOTH, BOTH)]:
        c = classify_crash(last, victim)
        print(f"  case {c.number}: last_sender={last:<8s} victim={victim:<8s}")
        print(f"     dilemma : {c.survivor_dilemma}")
        print(f"     action  : {c.recommended_action}")


def demo_fig_618() -> None:
    print("\n" + "=" * 70)
    print("FIG 6-18 STRATEGY MATRIX (no client strategy wins for all crash points)")
    print("=" * 70)
    crashes = [(False, False), (True, False), (False, True), (True, True)]
    crash_labels = ["none", "after_ack", "after_write", "after_both"]
    for server in ServerStrategy:
        print(f"\n  server={server.value}")
        print(f"  {'client':<28s}", end="")
        for cl in crash_labels:
            print(f" {cl:>12s}", end="")
        print()
        for client in ClientStrategy:
            print(f"  {client.value:<28s}", end="")
            for ca, cw in crashes:
                o = fig_618_outcome(server, client, ca, cw)
                print(f" {o:>12s}", end="")
            print()


def demo_two_army() -> None:
    print("\n" + "=" * 70)
    print("TWO-ARMY: distinct message kinds per k-round protocol")
    print("=" * 70)
    for k in (1, 2, 3, 5, 10):
        print(f"  k={k:2d} rounds -> {two_army_worst_case_messages(k):3d} message kinds, "
              f"last one still unconfirmed")


def demo_fsm() -> None:
    print("\n" + "=" * 70)
    print("SENDER FSM (OPEN -> SEND -> ACK -> SEND -> CRASH -> TIMEOUT -> RST)")
    print("=" * 70)
    fsm = TransferFSM(user_timeout_seconds=4.0)
    for e in [Evt.OPEN, Evt.SEND, Evt.ACK, Evt.SEND, Evt.CRASH, Evt.TIMEOUT]:
        fsm.step(e)
    print(f"  {'prev':<10s} {'event':<10s} -> {'next':<10s} note")
    for prev, evt, nxt, note in fsm.trace:
        print(f"  {prev.name:<10s} {evt.name:<10s} -> {nxt.name:<10s} {note}")


def main() -> None:
    demo_seven_cases()
    demo_fig_618()
    demo_two_army()
    demo_fsm()
    print("\nDone. Edit `for e in [..]` in demo_fsm() to drive your own scenarios.")


if __name__ == "__main__":
    main()
