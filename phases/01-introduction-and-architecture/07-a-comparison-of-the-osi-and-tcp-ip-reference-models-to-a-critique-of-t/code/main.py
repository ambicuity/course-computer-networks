#!/usr/bin/env python3
"""Compare the OSI and TCP/IP reference models and apply both critiques.

This stdlib-only program encodes the differences from Tanenbaum's comparison
(OSI vs TCP/IP) and the two critiques into a deterministic scorecard. It:

  1. Prints the 7-layer OSI -> 4-layer TCP/IP overlay.
  2. Scores each model against design criteria drawn straight from the
     critiques (service/interface/protocol split, physical-vs-data-link
     separation, generality, transport flexibility, layer parsimony,
     protocol maturity at model-design time).
  3. Recommends a model for a concrete architecture-review scenario and
     explains which single criterion decided it.

No network calls, no third-party packages. Run: python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


# --- Layer overlay -----------------------------------------------------------

# OSI layer number -> (OSI name, TCP/IP layer it maps to, note)
LAYER_OVERLAY: list[tuple[int, str, str, str]] = [
    (7, "Application", "Application", "TCP/IP folds OSI 5-7 into one layer"),
    (6, "Presentation", "Application", "nearly empty in OSI; TLS/JSON live in apps"),
    (5, "Session", "Application", "nearly empty in OSI; dialog control rarely a layer"),
    (4, "Transport", "Transport", "OSI: conn-oriented only; TCP/IP: TCP or UDP"),
    (3, "Network", "Internet", "OSI: both modes; TCP/IP: connectionless IP only"),
    (2, "Data Link", "Host-to-Network", "TCP/IP merges L1+L2 here"),
    (1, "Physical", "Host-to-Network", "OSI keeps it separate; TCP/IP does not"),
]


# --- Critique-derived scoring criteria ---------------------------------------

@dataclass(frozen=True)
class Criterion:
    """A single design property either model may or may not satisfy."""

    key: str
    question: str
    osi: bool
    tcpip: bool
    rationale: str


CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        key="siv_split",
        question="Cleanly separates service / interface / protocol?",
        osi=True,
        tcpip=False,
        rationale="OSI's biggest contribution; TCP/IP internet layer only offers "
        "SEND/RECEIVE IP PACKET, so it is a poor guide for new designs.",
    ),
    Criterion(
        key="phys_link_split",
        question="Separates the physical and data-link layers?",
        osi=True,
        tcpip=False,
        rationale="Transmission media vs frame delimiting are different jobs; "
        "TCP/IP lumps them into host-to-network.",
    ),
    Criterion(
        key="general",
        question="General enough to describe non-native stacks?",
        osi=True,
        tcpip=False,
        rationale="Model-first OSI is unbiased; describing Bluetooth with the "
        "TCP/IP model is impossible.",
    ),
    Criterion(
        key="transport_choice",
        question="Lets transport be connectionless when useful?",
        osi=False,
        tcpip=True,
        rationale="OSI mandates connection-oriented transport; TCP/IP allows UDP, "
        "which wins for simple request-response.",
    ),
    Criterion(
        key="parsimony",
        question="Avoids near-empty layers (layer parsimony)?",
        osi=False,
        tcpip=True,
        rationale="OSI session + presentation are nearly empty; 7 layers was "
        "'more political than technical'.",
    ),
    Criterion(
        key="protocol_maturity",
        question="Model built from already-deployed, proven protocols?",
        osi=False,
        tcpip=True,
        rationale="OSI defined the model before protocols (needing convergence "
        "sublayers); TCP/IP described working protocols.",
    ),
    Criterion(
        key="layer_is_layer",
        question="Every named layer is a true layer, not an interface?",
        osi=True,
        tcpip=False,
        rationale="TCP/IP host-to-network is really an interface between network "
        "and data-link concerns.",
    ),
)


# --- Transport placement table ----------------------------------------------

@dataclass(frozen=True)
class Transport:
    name: str
    rfc: str
    header_bytes: int
    connection: str
    reliability: str


TRANSPORTS = (
    Transport("UDP", "RFC 768", 8, "none", "best-effort"),
    Transport("TCP", "RFC 793", 20, "3-way handshake", "ordered + retransmit"),
)


# --- Scenario engine ---------------------------------------------------------

@dataclass(frozen=True)
class Scenario:
    """An architecture-review question, expressed as criterion weights.

    Positive weight favours whichever model satisfies the criterion.
    """

    name: str
    weights: dict[str, int] = field(default_factory=dict)


def score_model(is_osi: bool, scenario: Scenario) -> int:
    """Weighted score for one model under a scenario."""
    total = 0
    for crit in CRITERIA:
        satisfied = crit.osi if is_osi else crit.tcpip
        if satisfied:
            total += scenario.weights.get(crit.key, 0)
    return total


def deciding_criterion(scenario: Scenario) -> Criterion:
    """The criterion with the largest weight that the two models disagree on."""
    contested = [
        c
        for c in CRITERIA
        if c.osi != c.tcpip and scenario.weights.get(c.key, 0) > 0
    ]
    return max(contested, key=lambda c: scenario.weights.get(c.key, 0))


def recommend(scenario: Scenario) -> tuple[str, int, int, Criterion]:
    osi = score_model(True, scenario)
    tcp = score_model(False, scenario)
    winner = "OSI" if osi > tcp else ("TCP/IP" if tcp > osi else "tie")
    return winner, osi, tcp, deciding_criterion(scenario)


# --- Rendering ---------------------------------------------------------------

def render_overlay() -> None:
    print("OSI (7 layers)  ->  TCP/IP (4 layers)")
    print("-" * 64)
    for num, osi_name, tcp_name, note in LAYER_OVERLAY:
        print(f"  L{num} {osi_name:<13} -> {tcp_name:<16} ({note})")
    print()


def render_scorecard() -> None:
    print("Critique-derived scorecard")
    print("-" * 64)
    print(f"  {'criterion':<46}{'OSI':>6}{'TCP/IP':>8}")
    osi_total = tcp_total = 0
    for crit in CRITERIA:
        osi_total += int(crit.osi)
        tcp_total += int(crit.tcpip)
        print(f"  {crit.question:<46}{_mark(crit.osi):>6}{_mark(crit.tcpip):>8}")
    print(f"  {'TOTAL (criteria satisfied)':<46}{osi_total:>6}{tcp_total:>8}")
    print()


def render_transports() -> None:
    print("Transport placement (where TCP/IP gives a choice OSI forbids)")
    print("-" * 64)
    print(f"  {'proto':<6}{'rfc':<10}{'hdr':>5}  {'connection':<16}{'reliability'}")
    for t in TRANSPORTS:
        print(
            f"  {t.name:<6}{t.rfc:<10}{t.header_bytes:>4}B  "
            f"{t.connection:<16}{t.reliability}"
        )
    print()


def _mark(value: bool) -> str:
    return "yes" if value else "no"


def render_recommendation(scenario: Scenario) -> None:
    winner, osi, tcp, decider = recommend(scenario)
    print(f"Scenario: {scenario.name}")
    print("-" * 64)
    print(f"  OSI score = {osi}   TCP/IP score = {tcp}   -> recommend: {winner}")
    print(f"  deciding criterion: {decider.question}")
    print(f"    {decider.rationale}")
    print()


def main() -> None:
    print("=" * 64)
    print("OSI vs TCP/IP: comparison and critique")
    print("=" * 64)
    print()

    render_overlay()
    render_scorecard()
    render_transports()

    # Scenario A: a forward-looking, technology-neutral standards effort.
    future_stack = Scenario(
        name="Design a brand-new IoT protocol family meant to outlive today's radios",
        weights={
            "siv_split": 4,
            "general": 5,
            "phys_link_split": 3,
            "layer_is_layer": 2,
            "transport_choice": 1,
        },
    )
    render_recommendation(future_stack)

    # Scenario B: ship a pragmatic IP product fast.
    ship_ip = Scenario(
        name="Ship an IP-based product quickly using proven, deployed protocols",
        weights={
            "protocol_maturity": 5,
            "parsimony": 3,
            "transport_choice": 4,
        },
    )
    render_recommendation(ship_ip)


if __name__ == "__main__":
    main()
