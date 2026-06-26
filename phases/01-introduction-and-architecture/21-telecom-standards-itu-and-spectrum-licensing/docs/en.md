# The Telecommunications World: ITU, Spectrum Auctions, and ITU-T WG

> The International Telecommunication Union, founded in 1865 to standardize telegraphy and a UN agency since 1947, splits into three sectors: **ITU-T** (telecom standardization, formerly CCITT), **ITU-R** (radiocommunications, which coordinates global use of the radio frequency spectrum and defines the unlicensed ISM bands 902-928 MHz, 2.4-2.5 GHz, 5.725-5.825 GHz), and **ITU-D** (development). ITU-T does its real work in roughly 10 **Study Groups** — SG15 writes the DSL family (G.992 ADSL, G.984 GPON), SG16 wrote **H.264** (also ISO MPEG-4 AVC), SG17 owns **X.509** public-key certificates, SG2 owns the **E.164** international numbering plan. The scarce resource in mobile networks is radio spectrum: governments license exclusive blocks via **spectrum auctions** such as the simultaneous multi-round ascending (SMRA) auction — the UK's 2000 3G auction raised about $40 billion for five licenses — and the operator's payoff for owning a clean block is **frequency reuse**, where a hexagonal cellular layout reuses each frequency once every S = i² + i·j + j² cells (S=7 for i=2, j=1). Unlicensed spectrum, used by 802.11 (WiFi), avoids the auction cost but trades it for power limits and coexistence with cordless phones and microwave ovens. The lesson builds a runnable SMRA auction, a reuse-cluster planner, and a Study Group classifier so you can see the actual numbers and assignments behind the standards.

**Type:** Learn
**Languages:** Python
**Prerequisites:** The telephone/cellular network model from Phase 1's example-networks lessons; basic radio vocabulary (frequency band, channel)
**Time:** ~80 minutes

## Learning Objectives

- Name ITU's three sectors (ITU-T, ITU-R, ITU-D) and give one concrete output of each: an ITU-T recommendation series, a spectrum coordination role, a development mandate.
- Map a recommendation string (H.264, X.509, G.992.1, E.164, Q.931) onto the ITU-T Study Group that owns it and explain why recommendations are technically non-binding yet practically mandatory.
- Describe how a simultaneous multi-round ascending auction assigns licenses, including the activity rule that forces bidders to keep bidding or lose eligibility.
- Compute the cellular reuse cluster size S = i² + i·j + j² and the per-cell channel count for a given band, and explain the trade-off between reuse factor and capacity.
- Contrast licensed spectrum (exclusive, auctioned, clean reuse) with unlicensed ISM bands (shared, power-capped, used by 802.11) and justify which a designer picks.

## The Problem

A national regulator has a paired block of spectrum to assign — say 60 MHz in the 2.1 GHz band — and three mobile operators who each want enough contiguous spectrum to build a nationwide 3G network. If the regulator just hands blocks out for free, operators over-claim and the spectrum is wasted; if it picks winners politically, litigation and inefficiency follow. The regulator needs a mechanism that reveals who values the spectrum most and assigns exclusive licenses cleanly. Meanwhile the winning operator's RF engineer has a different problem: given 840 channels in the won band and a hexagonal grid of cells, how often can each frequency be reused before co-channel interference becomes intolerable? And a standards engineer reading a spec that says "use H.264 and present an X.509 certificate" wants to know which working group actually wrote each, in case they need to file a defect or track a revision. Three questions, one thread: scarce radio resource + global coordination body + the working groups that turn coordination into deployable standards.

## The Concept

### ITU: one body, three sectors, ~200 governments

ITU is the oldest intergovernmental technical body still in operation. Founded in 1865 to standardize telegraphy (so half the world's Morse code did not collide with the other half's), it took over telephony when the telephone went international and became a UN specialized agency in 1947. It has about 200 governmental members — almost every UN member — plus more than 700 sector and associate members (AT&T, Vodafone, Cisco, Nokia, Intel, Microsoft, Boeing, VeriSign). The United States, having no national PTT (Post, Telegraph & Telephone administration), is represented by the State Department. The textbook's punchline is that worldwide telephone-company legal status ranges from the U.S. extreme of over 2000 mostly-tiny privately owned carriers to countries where a government monopoly runs mail, telegraph, telephone, and broadcast — and that the trend is liberalization and privatization, which makes inter-country compatibility standards only more important.

ITU's work splits across three sectors:

| Sector | Full name | Concern | Representative output |
|---|---|---|---|
| **ITU-T** | Telecommunication Standardization Sector (was CCITT, the French *Comité Consultatif International Télégraphique et Téléphonique*, pre-1993) | telephone and data communication interfaces | H.264, X.509, G.992, E.164, Q.931 |
| **ITU-R** | Radiocommunication Sector | global coordination of radio frequencies | Radio Regulations, ISM band definitions, IMT-2000/Advanced (3G/4G) |
| **ITU-D** | Development Sector | ICT deployment, narrowing the digital divide | development programs, not standards |

`assets/telecom-itu-spectrum-licensing.svg` shows the three-sector split with the ITU-T recommendation series and ITU-R's ISM bands called out under each box.

### ITU-T Study Groups: where recommendations actually come from

ITU-T's task is to issue technical *recommendations* about telephone, telegraph, and data interfaces. The word "recommendation" is deliberate: technically a country is free to adopt a different standard, but in practice a country that goes its own way cuts itself off from everyone else. The real work happens in **Study Groups (SGs)**, currently about ten of them, each up to ~400 people, subdivided into Working Parties, Expert Teams, and ad hoc groups. ITU-T has issued over 3000 recommendations. The series letter encodes the topic family:

| Series | Topic family | Owning Study Group | Canonical example |
|---|---|---|---|
| H | Audiovisual/multimedia coding | SG16 | **H.264** / MPEG-4 AVC video compression |
| X | Data networks and security | SG17 | **X.509** public-key certificates (used in TLS and S/MIME) |
| G | Transmission systems and media | SG15 | **G.992.1** ADSL, **G.984** GPON |
| Q | Switching and signalling | SG11 | **Q.931** ISDN call control |
| E | Overall network operation, numbering | SG2 | **E.164** international telephone number plan |
| Y | Next-generation networks, OAM | SG13 | **Y.1731** Ethernet OAM |
| Z | Languages and software | SG17 | **Z.100** SDL (Specification and Description Language) |

`code/main.py` ships a `classify_recommendation()` that maps any "X.509"-style string onto the owning SG — run it and confirm H.264 lands on SG16, X.509 on SG17, G.992.1 on SG15. This is the lookup an engineer does before filing a contribution or a defect against a standard.

### ITU-R and the spectrum: licensed blocks vs unlicensed ISM

ITU-R coordinates worldwide use of the radio frequency spectrum to keep competing interests from jamming each other across borders, and it runs the World Radiocommunication Conference (WRC) that revises the binding Radio Regulations. National regulators then take ITU-R's allocation and assign the actual licenses.

There are two fundamentally different paths for a radio system to get spectrum:

| Path | How you get it | Cost | What you get | Who uses it |
|---|---|---|---|---|
| **Licensed** | Win a government auction (e.g. SMRA) | high (UK 2000: ~$40B for five 3G licenses) | exclusive, interference-protected block, predictable reuse | mobile phone operators (GSM, UMTS, LTE) |
| **Unlicensed (ISM)** | Just transmit, obeying a power cap | free | shared band, must coexist with cordless phones, microwave ovens, garage doors | 802.11 (WiFi), Bluetooth, cordless phones |

The ISM bands ITU-R defines — 902-928 MHz, 2.4-2.5 GHz, 5.725-5.825 GHz — are the textbook's "opposite" choice: instead of an expensive exclusive auction, 802.11 takes the ISM band and limits transmit power so many devices coexist. The cost is that a WiFi radio competes with a microwave oven for the channel.

### Spectrum auctions: the simultaneous multi-round ascending (SMRA) design

The dominant mechanism for assigning multiple related licenses is the **SMRA** (simultaneous multi-round ascending) auction, used for spectrum from the late 1990s onward. All licenses are bid on at the same time, in rounds. In each round a bidder may place bids on a set of licenses up to its **eligibility** (a license-count cap that starts at the number of licenses it wants). The **activity rule** is the key design: if a bidder stops bidding on a license, its eligibility for future rounds shrinks. This forces bidders to bid aggressively early — they cannot sit out and pounce at the end — and it exposes information about which licenses are contested so prices can climb toward true valuations. A round with no new bids raising any price closes the auction.

Worked example (from `code/main.py`, four licenses A-D, three bidders, initial eligibility 2 each):

| Round | Contested license | Bids raise price | Notes |
|---|---|---|---|
| 1 | B (Verizon 110, Vodafone 115), C (Vodafone 100, Telefonica 105) | A=120, B=115, C=105, D=95 | opening bids on all four |
| 2 | B (Verizon 125), C (Telefonica 120) | A=130, B=125, C=120 | activity rule keeps bidders in |
| 3 | C (Vodafone 130, Telefonica 140) | C=140 | final contest on the most desired block |
| 4 | none | — | no raises → auction closes |

Final: A→Verizon 130M, B→Verizon 125M, C→Telefonica 140M, D→Telefonica 95M, total 490M. The activity rule is what stopped Vodafone from waiting — its eligibility collapsed when it stopped bidding on B, so it had to keep raising C or drop out.

### Cellular frequency reuse: why a clean licensed block pays off

Spectrum scarcity is what drove the **cellular** design: instead of one high-power transmitter covering a whole city, the coverage area is tiled with cells, each with a low-power base station, so the same frequency can be reused in non-adjacent cells. On a hexagonal grid the set of cells that must all use different frequencies before a frequency repeats is the **reuse cluster**, of size

**S = i² + i·j + j²**

where (i, j) are the integer shift parameters of the reuse pattern. The larger S, the less co-channel interference but the fewer channels per cell. If the operator owns N channels in its licensed block, each cell gets N/S channels.

Worked example, band of 840 channels (from `code/main.py`):

| i | j | S = i²+i·j+j² | channels/cell | trade-off |
|---|---|---|---|---|
| 1 | 0 | 1 | 840 | no reuse, max capacity, worst interference |
| 1 | 1 | 3 | 280 | tight reuse, needs careful power control |
| 2 | 0 | 4 | 210 | common early analog pattern |
| 2 | 1 | 7 | 120 | classic 7-cell reuse (GSM-style) |
| 2 | 2 | 12 | 70 | conservative, rural low-density |
| 3 | 2 | 19 | 44 | very conservative, heavy interference margin |

The S=7 (i=2, j=1) pattern is the textbook canonical case: each frequency is reused once every 7 cells, giving 840/7 = 120 channels per cell. The SVG marks the f1 cell and its reuse partner seven cells away in the same color. 1G AMPS assigned each call a specific frequency and reused it carefully across cells; modern 3G UMTS lets every cell use all frequencies but tolerates a controlled level of CDMA interference, so the reuse factor effectively drops toward 1 at the cost of sophisticated power control. Owning a licensed block is what makes this planning predictable — you know no one else is transmitting in your band.

### Standards people, meeting people: ITU-T vs IETF vs IEEE

The textbook draws a sharp cultural contrast. ITU-T and ISO meetings are populated by corporate officials and government representatives; governments are members and the process is treaty-flavored and slow. The IETF — which writes the RFCs the Internet actually runs on — is open, runs on "rough consensus and running code," and its participants are individual engineers. IEEE (which wrote 802.3 Ethernet and 802.11 WiFi) sits in between, society-governed but engineer-driven. The practical consequence: a phone standard touches national regulators and numbering plans, so it lives in ITU-T; an Internet protocol lives in an IETF RFC. 3GPP (Third Generation Partnership Project) is the collaboration of telecom associations that actually writes the UMTS/LTE/5G specifications, coordinating with ITU-R's IMT requirements. Knowing which body owns a standard tells you where to file a defect, where the next revision is debated, and whether the answer is binding or "just a recommendation."

## Build It

1. Read `code/main.py`. It implements three things: `run_smra_auction()` (a simultaneous multi-round ascending auction with the activity rule), `cluster_size()` / `per_cell_channels()` (the cellular reuse math S = i²+i·j+j²), and `classify_recommendation()` (the ITU-T Study Group lookup).
2. Run it: `python3 code/main.py`. Confirm the auction closes after 4 rounds with the totals printed, the reuse table shows S=7 → 120 channels/cell, and H.264 maps to SG16.
3. Edit the `rounds` list in `main()` — add a late bid on license D — and rerun. Watch the auction take an extra round and the winner of D change; the activity rule means a bidder who wants D late must have kept eligibility.
4. Change the band from 840 to 1000 channels and rerun `reuse_table`. Confirm S=7 now gives 142 channels/cell (1000//7).
5. Add a new series to `SERIES_TO_SG` (e.g. `"V": "SG12 (test methods)"`) and call `classify_recommendation("V.50")` to confirm the lookup works.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm an auction assigned all licenses | per-license winner + price, total revenue, round count | auction closes only after a round with zero raises; every license has a winner |
| Verify the activity rule bit | eligibility shrank for bidders who stopped bidding | a bidder that sits out a round cannot bid on more licenses next round |
| Justify a reuse choice | S = i²+i·j+j² and channels/cell for the chosen band | S=7 is the classic GSM trade-off; S=1 maximizes capacity but needs CDMA power control |
| Map a standard to its WG | `classify_recommendation()` output | H.264→SG16, X.509→SG17, G.992.1→SG15 — matches the series-letter convention |
| Pick licensed vs unlicensed | cost, exclusivity, coexistence | mobile operator pays auction for clean reuse; WiFi takes ISM and power-limits |

## Ship It

Produce one artifact under `outputs/`:

- An annotated auction trace (`outputs/prompt-telecom-itu-spectrum-licensing.md`): the round-by-round bid history, the eligibility collapse, final winners and revenue, and a one-paragraph note on why SMRA (activity rule + simultaneous bidding) beats a sealed-bid beauty contest for spectrum assignment.
- A reuse-planning card: for a band size you choose, the (i,j,S,channels/cell) table and the recommended pattern with a one-sentence justification of the interference/capacity trade-off.
- A Study Group cheat-sheet: ten common recommendations mapped to their SG, with one real product that depends on each (e.g. X.509 → TLS browser certificates).

Start from the printed output of `code/main.py` and annotate it.

## Exercises

1. In the `code/main.py` auction, Vodafone wins nothing despite bidding 130 on C in round 3. Explain exactly why — what did the activity rule do to Vodafone's eligibility, and what would Vodafone have had to do differently in round 2 to stay in the fight for C?
2. An operator wins a 2×10 MHz paired block (60 MHz total, 840 channels of 50 kHz each) and wants S=7 reuse. Compute channels per cell. Then it deploys 120-cell sectored antennas (3 sectors per cell). How many channels per sector, and why does sectoring let it shrink S?
3. A WiFi designer picks the 2.4-2.5 GHz ISM band instead of bidding in a 2.1 GHz auction. List three concrete coexistence problems the WiFi radio must handle that a licensed UMTS operator does not, and name the 802.11 technique (CSMA/CA, OFDM, spread spectrum) that addresses each.
4. Classify these into the owning ITU-T Study Group and give one product that uses each: H.265, X.509, G.984.2, Q.1902, E.212. For E.212 specifically, explain why a mobile numbering/identity standard lives in ITU-T and not in an IETF RFC.
5. The UK 2000 3G auction raised ~$40B for five licenses. Sketch why a simultaneous multi-round ascending auction produces higher revenue and better license-to-bidder matching than a sealed-bid first-price auction, and name one failure mode (exposure risk) that SMRA still suffers when licenses are complements.
6. Compare the standards process for adding a new SIP header (IETF, RFC 3261 lineage) versus adding a new field to Q.931 (ITU-T, SG11). For each, name the body, the document type, and whether the result is binding on a national regulator.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| ITU-T | "the phone standards people" | Telecommunication Standardization Sector (was CCITT); writes the H./X./G./Q./E. recommendation series in Study Groups |
| ITU-R | "the radio people" | Radiocommunication Sector; coordinates global spectrum, runs the WRC, defines the ISM bands |
| Study Group (SG) | "a committee" | An ITU-T working group of up to ~400 people that owns a recommendation series (SG15→DSL, SG16→video, SG17→security) |
| Recommendation | "a standard" | Technically a non-binding suggestion; practically mandatory because going your own way cuts you off from the global network |
| Spectrum auction | "selling airwaves" | A government mechanism (often SMRA) that assigns exclusive licenses to spectrum blocks to the highest-value bidder |
| SMRA | "that auction" | Simultaneous multi-round ascending auction: all licenses bid at once, in rounds, with an activity rule that shrinks eligibility if you stop bidding |
| Activity rule | "keep bidding or leave" | A bidder may bid on at most `eligibility` licenses per round; stopping shrinks future eligibility, forcing early aggressive bidding |
| Frequency reuse | "reusing channels" | Reusing the same frequency in non-adjacent cells of a cellular layout; cluster size S = i²+i·j+j² |
| Reuse cluster (S) | "the reuse factor" | Number of cells that must use distinct frequencies before a frequency repeats; larger S → less interference, fewer channels/cell |
| ISM band | "free spectrum" | Industrial/Scientific/Medical unlicensed bands ITU-R defines (902-928 MHz, 2.4-2.5 GHz, 5.725-5.825 GHz); power-capped, shared |
| PTT | "the post office" | Post, Telegraph & Telephone administration — the nationalized monopoly that ran comms in much of the world before liberalization |
| 3GPP | "the mobile standards group" | Third Generation Partnership Project; the telecom-association collaboration that actually writes UMTS/LTE/5G specs against ITU-R's IMT requirements |

## Further Reading

- **ITU-T Recommendation H.264** — Advanced video coding for generic audiovisual services (also ISO/IEC 14496-10, MPEG-4 AVC).
- **ITU-T Recommendation X.509** — Information technology — Open Systems Interconnection — The Directory: Public-key and attribute certificate frameworks (the certificate format used by TLS and S/MIME).
- **ITU-T Recommendation G.992.1** — Asymmetric Digital Subscriber Line (ADSL) transceivers; **G.984** — Gigabit-capable Passive Optical Network (GPON), both from SG15.
- **ITU-T Recommendation E.164** — The international public telecommunication numbering plan (country codes, max 15 digits).
- **ITU-T Recommendation Q.931** — Digital subscriber signalling system No. 1 — ISDN user-network interface layer 3 specification (SG11).
- **ITU-R Radio Regulations** — the binding international treaty on spectrum allocation, revised at the World Radiocommunication Conference.
- **ITU-R Recommendation M.1645 / IMT-2000** — the 3G requirements framework (2 Mbps stationary, 384 kbps mobile).
- **IEEE 802.11** — Wireless LAN MAC and PHY specifications (ISM-band operation, CSMA/CA, OFDM in 802.11a/g).
- Milgrom, *Putting Auction Theory to Work* — the SMRA design and the activity rule, written by the auction's architect.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Section 1.6.1 ("Who's Who in the Telecommunications World") and Section 1.5.4 (the cellular/mobile-phone network).
