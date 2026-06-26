#!/usr/bin/env python3
"""BGP Route Leak and AS Path Forgery (Lab 11).

Reference oracle for the BGP incident-response workflow. Consumes
a stream of BGP UPDATE-like events, applies an import policy
(enforce-first-as, RPKI Route Origin Validation per RFC 6811),
and classifies each UPDATE as accepted, rejected, leak-suspect,
or hijack-suspect.

Scenarios:
  1) legitimate       AS64600 originates 203.0.113.0/24.
                      ROV: Valid. Policy: pass. Verdict: OK.
  2) route_leak       AS64555 (customer of AS64666) re-announces
                      the prefix. ROV: NotFound (no ROA on
                      origin=64555). Detector: leak.
  3) as_path_forgery  AS64888 announces the prefix with itself
                      as origin. ROV: Invalid (ROA says 64600).
                      Detector: hijack.

Run:  python3 code/main.py --scenario route_leak
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

# ROA table: (prefix, max_length, origin_asn). RFC 6482.
ROA_TABLE: dict[str, tuple[str, int, int]] = {
    "203.0.113.0/24": ("203.0.113.0", 24, 64600),
    "198.51.100.0/24": ("198.51.100.0", 24, 64600),
}

PEER_AS: dict[str, int] = {
    "AS64600": 64600, "AS64666": 64666, "AS64555": 64555,
    "AS64888": 64888, "AS64700": 64700,
}

# True origin per prefix (per IRR / RPKI ROA). Used by leak detector.
TRUE_ORIGIN: dict[str, int] = {
    "203.0.113.0/24": 64600,
    "198.51.100.0/24": 64600,
}


@dataclass
class Update:
    """A simplified BGP UPDATE: prefix + AS_PATH + next_hop + peer."""
    prefix: str
    as_path: list[int]
    next_hop: str
    peer: str
    origin_igp: bool = True  # ORIGIN attribute: 1=IGP, 2=EGP, 3=INCOMPLETE


def prefix_in_roa(prefix: str) -> tuple[str, int, int] | None:
    return ROA_TABLE.get(prefix)


def rpki_validate(upd: Update) -> str:
    """RFC 6811: classify UPDATE as Valid / Invalid / NotFound.
    Only the rightmost (origin) ASN is validated."""
    if not upd.as_path:
        return "Invalid"  # RFC 4271: empty AS_PATH rejected
    roa = prefix_in_roa(upd.prefix)
    origin = upd.as_path[-1]
    if roa is None:
        return "NotFound"
    if origin == roa[2]:
        return "Valid"
    return "Invalid"


def import_policy(upd: Update) -> str:
    """enforce-first-as: first ASN must equal the peer's AS."""
    if not upd.as_path:
        return "REJECT: empty AS_PATH"
    expected = PEER_AS.get(upd.peer)
    if expected != upd.as_path[0]:
        return f"REJECT: first AS {upd.as_path[0]} != peer AS {expected}"
    return "ACCEPT"


def detect_leak_or_hijack(upd: Update) -> str:
    """Cross-check the rightmost (origin) ASN against the known
    true origin for the prefix."""
    true_origin = TRUE_ORIGIN.get(upd.prefix)
    if true_origin is None:
        return "unknown prefix"
    if upd.as_path[-1] != true_origin:
        return f"LEAK/HIJACK suspect: origin {upd.as_path[-1]} != true origin {true_origin}"
    return "origin matches"


def process(upd: Update) -> str:
    rov = rpki_validate(upd)
    policy = import_policy(upd)
    detector = detect_leak_or_hijack(upd)
    return f"ROV={rov:<9} policy={policy:<55} detector={detector}"


def show(label: str, upd: Update) -> None:
    print("=" * 78)
    print(f"BGP ORACLE  --  {label}")
    print("=" * 78)
    print(f"  UPDATE prefix={upd.prefix} peer={upd.peer} "
          f"AS_PATH={upd.as_path} next_hop={upd.next_hop}")
    print(f"  {process(upd)}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--scenario",
                        choices=("legitimate", "route_leak", "as_path_forgery"),
                        default="route_leak")
    args = parser.parse_args()

    if args.scenario == "legitimate":
        show("legitimate (AS64600 originates)",
             Update("203.0.113.0/24", [64600], "198.51.100.1", "AS64600"))

    elif args.scenario == "route_leak":
        # In the in-lab simulation we keep the ROA for 203.0.113.0/24 with
        # origin=64600, so the leaking UPDATE is flagged Invalid by ROV.
        # Real leaks reach networks that do NOT run ROV, in which case the
        # UPDATE is NotFound and propagates. Both paths lead to the same
        # operational answer: install an IRR-based prefix-list filter on
        # the customer session.
        show("route_leak (AS64555 customer -> AS64666 transit -> AS64700)",
             Update("203.0.113.0/24", [64666, 64555], "192.0.2.66", "AS64666"))
        print("  ROV verdict: Invalid (ROA binds 203.0.113.0/24 to origin=64600,")
        print("        UPDATE's origin is 64555).  A transit running ROV drops it.")
        print("  ROV alone is not enough: it does not protect networks that have")
        print("        not deployed ROV, and it does not catch all leak shapes.")
        print("  Defense: AS64666 needs an IRR-based prefix-list filter on its")
        print("        import from AS64555 that limits 64555 to announcing only")
        print("        64555's own allocated space, plus enforce-first-as, plus a")
        print("        MAXPREFIX ceiling to bound blast radius.")

    elif args.scenario == "as_path_forgery":
        show("as_path_forgery (AS64888 claims origin)",
             Update("203.0.113.0/24", [64888], "192.0.2.88", "AS64888"))
        print("  ROV says Invalid because the ROA binds 203.0.113.0/24")
        print("        to origin=64600, and the UPDATE's origin is 64888.")
        print("  A well-run transit drops the UPDATE before it propagates.")


if __name__ == "__main__":
    main()
