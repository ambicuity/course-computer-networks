"""Telecom standards, spectrum licensing, and ITU-T working groups.

A runnable, stdlib-only model that ties the lesson's three mechanisms together:

  1. A simultaneous multi-round ascending auction (SMRA) for paired spectrum
     licenses. Bidders accumulate licenses, lose eligibility when they stop
     bidding, and the auction closes when no new bids arrive. This is the
     mechanism governments use to assign the scarce radio spectrum that ITU-R
     coordinates globally.
  2. A cellular frequency-reuse planner. Given a reuse pattern, it computes
     the cluster size S = i^2 + i*j + j^2 and the per-cell capacity, which is
     the engineering payoff of owning a contiguous spectrum block.
  3. An ITU-T Study Group classifier that maps a recommendation series
     (H.264, X.509, G.992, etc.) onto the Study Group that produced it, so the
     reader can see which WG actually wrote a standard in use today.

No network calls, no third-party packages. Run:  python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 1. Spectrum auction: simultaneous multi-round ascending (SMRA)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Bid:
    bidder: str
    license_id: str
    amount: int          # in millions of currency units


@dataclass
class AuctionState:
    licenses: list[str]
    # current high bid + winner per license
    high_bid: dict[str, int] = field(default_factory=dict)
    high_bidder: dict[str, str] = field(default_factory=dict)
    # eligibility = number of licenses a bidder may still bid on per round
    eligibility: dict[str, int] = field(default_factory=dict)
    rounds: int = 0


def run_smra_auction(
    licenses: list[str],
    bidders: list[str],
    initial_eligibility: dict[str, int],
    round_bids: list[list[Bid]],
) -> AuctionState:
    """Run an SMRA auction round-by-round.

    Activity rule: a bidder may place bids on at most `eligibility` licenses
    in a round. Any license it stops bidding on drops from its eligibility, so
    aggressive early bidding is required to keep options open. The auction
    stops after a round in which no new bid raises any price.
    """
    st = AuctionState(
        licenses=list(licenses),
        high_bid={lic: 0 for lic in licenses},
        high_bidder={lic: None for lic in licenses},
        eligibility=dict(initial_eligibility),
    )
    for r, bids in enumerate(round_bids, start=1):
        st.rounds = r
        activity: dict[str, int] = {b: 0 for b in bidders}
        raised = False
        for bid in bids:
            if activity[bid.bidder] >= st.eligibility[bid.bidder]:
                continue  # activity rule: too many licenses this round
            current = st.high_bid[bid.license_id]
            if bid.amount > current:
                st.high_bid[bid.license_id] = bid.amount
                st.high_bidder[bid.license_id] = bid.bidder
                activity[bid.bidder] += 1
                raised = True
        # Shrink eligibility: a bidder keeps eligibility only for licenses it
        # actually bid on this round (activity rule).
        for b in bidders:
            st.eligibility[b] = min(st.eligibility[b], max(activity[b], 1))
        if not raised:
            break
    return st


def auction_summary(st: AuctionState) -> str:
    lines = [f"SMRA auction closed after {st.rounds} round(s)."]
    total = 0
    for lic in st.licenses:
        who = st.high_bidder[lic] or "(unsold)"
        amt = st.high_bid[lic]
        total += amt
        lines.append(f"  {lic}: {who} @ {amt}M")
    lines.append(f"  Total revenue: {total}M")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. Cellular frequency reuse
# ---------------------------------------------------------------------------


def cluster_size(i: int, j: int) -> int:
    """Reuse cluster size for a hexagonal cellular layout: S = i^2 + i*j + j^2."""
    if i < 0 or j < 0:
        raise ValueError("reuse parameters i, j must be non-negative")
    return i * i + i * j + j * j


def per_cell_channels(total_channels: int, i: int, j: int) -> int:
    """Channels available per cell after splitting the band into S reuse groups."""
    s = cluster_size(i, j)
    return total_channels // s


def reuse_table(total_channels: int) -> list[tuple[int, int, int, int]]:
    """Common reuse patterns: (i, j, S, channels/cell)."""
    out: list[tuple[int, int, int, int]] = []
    for i, j in [(1, 0), (1, 1), (2, 0), (2, 1), (2, 2), (3, 2)]:
        s = cluster_size(i, j)
        out.append((i, j, s, per_cell_channels(total_channels, i, j)))
    return out


# ---------------------------------------------------------------------------
# 3. ITU-T Study Group classifier
# ---------------------------------------------------------------------------

# Recommendation series -> Study Group (representative current mapping).
SERIES_TO_SG: dict[str, str] = {
    "H": "SG16 (Multimedia coding, e.g. H.264/MPEG-4 AVC)",
    "X": "SG17 (Security, e.g. X.509 public-key certificates)",
    "G": "SG15 (Transport/access, e.g. G.992 ADSL, G.984 GPON)",
    "Q": "SG11 (Signalling, e.g. Q.931 ISDN call control)",
    "E": "SG2 (Numbering/routing, e.g. E.164 international phone numbers)",
    "Y": "SG13 (Future networks/OAM, e.g. Y.1731)",
    "T": "SG17 (Legacy telematics/ICT security)",
    "Z": "SG17 (Languages and software)",
    "I": "SG13 (Legacy ISDN/B-ISDN)",
    "M": "SG4 (Network management, legacy TMN)",
}


def classify_recommendation(rec: str) -> str:
    """Map 'H.264', 'X.509', 'G.992.1' onto the Study Group that owns it."""
    rec = rec.strip().upper()
    if "." not in rec:
        return f"{rec}: not a recognizable ITU-T series"
    series = rec.split(".", 1)[0]
    return SERIES_TO_SG.get(series, f"{rec}: series {series} not in this table")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 64)
    print("SPECTRUM AUCTION (SMRA) -- 4 paired licenses, 3 bidders")
    print("=" * 64)
    licenses = ["A", "B", "C", "D"]
    bidders = ["Verizon", "Vodafone", "Telefonica"]
    elig = {"Verizon": 2, "Vodafone": 2, "Telefonica": 2}
    rounds = [
        # Round 1: opening bids
        [Bid("Verizon", "A", 120), Bid("Verizon", "B", 110),
         Bid("Vodafone", "B", 115), Bid("Vodafone", "C", 100),
         Bid("Telefonica", "C", 105), Bid("Telefonica", "D", 95)],
        # Round 2: raise on contested B and C
        [Bid("Verizon", "B", 125), Bid("Vodafone", "C", 110),
         Bid("Telefonica", "C", 120), Bid("Verizon", "A", 130)],
        # Round 3: final contest on C
        [Bid("Vodafone", "C", 130), Bid("Telefonica", "C", 140)],
        # Round 4: no raises -> auction closes
        [],
    ]
    st = run_smra_auction(licenses, bidders, elig, rounds)
    print(auction_summary(st))
    print("  Eligibility left:", st.eligibility)

    print()
    print("=" * 64)
    print("FREQUENCY REUSE -- band of 840 channels split into clusters")
    print("=" * 64)
    print("  i  j   S(cluster)  channels/cell")
    for i, j, s, ch in reuse_table(840):
        flag = " <-- tightest reuse, max capacity" if s == 1 else ""
        print(f"  {i}  {j}   {s:>3}         {ch:>4}{flag}")
    print(f"  S=7 (i=2,j=1): each frequency reused once every 7 cells,")
    print(f"  capacity/cell = 840/7 = {per_cell_channels(840, 2, 1)} channels.")

    print()
    print("=" * 64)
    print("ITU-T STUDY GROUP CLASSIFIER")
    print("=" * 64)
    for rec in ["H.264", "X.509", "G.992.1", "E.164", "Y.1731", "Q.931", "Z.100"]:
        print(f"  {rec:<10} -> {classify_recommendation(rec)}")

    print()
    print("Takeaways:")
    print(" - ITU-R coordinates spectrum; governments AUCTION licenses (SMRA).")
    print(" - Owning a clean block lets an operator plan REUSE clusters")
    print("   (S = i^2 + i*j + j^2).")
    print(" - ITU-T STUDY GROUPS write the H./X./G./Q. series recommendations")


if __name__ == "__main__":
    main()
