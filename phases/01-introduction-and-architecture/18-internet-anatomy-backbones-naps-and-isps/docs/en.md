# Internet Anatomy: Backbones, NAPs, IXPs, and Tier-1 ISPs

> The Internet is not one network but a loose confederation of independently operated networks held together by routing policy and a handful of business relationships. At the bottom sit access ISPs that own the "last mile" (DSLAMs on telephone lines, CMTSes on cable plants, OLTs for FTTH) and hand customer packets to a **POP** (Point of Presence). Above them regional and national ISPs form a **backbone** of long-distance fiber and core routers; at the top a small set of **tier-1 ISPs** (AT&T, Sprint, NTT, Lumen, Telia) operate international backbones and buy **transit** from nobody. Networks exchange traffic at an **IXP** (Internet eXchange Point), literally a room full of routers joined by a LAN — AMS-IX, DE-CIX, LINX each shuffle hundreds of gigabits per second. Its ancestor was the **NAP** (Network Access Point), four of which NSF funded in 1994 to broker the handoff from the government-run NSFNET (a 45-Mbps ANSNET of IBM PC-RT routers and MCI fiber) to competing commercial backbones. Whether a packet goes direct across a **peering** link or detours through paid **transit** is decided by the **valley-free** rule (Gao 2001): paths may climb customer-to-provider, traverse at most one peer-to-peer link, then descend provider-to-customer — never "down then up," which would make someone carry traffic for free. `code/main.py` implements exactly this policy on a sample AS graph and prints the hop-by-hop path, which is what `traceroute` exposes as the real anatomy.

**Type:** Learn
**Languages:** shell, traceroute
**Prerequisites:** Packet switching and store-and-forward forwarding, the TCP/IP layered model, IP addressing and the role of routers
**Time:** ~80 minutes

## Learning Objectives

- Name the physical and logical pieces of the Internet edge (DSLAM, CMTS, OLT, cable/DSL modem, POP) and say where digital packets begin.
- Distinguish a **transit** (paid customer-to-provider) relationship from a **peering** (settlement-free, peer-to-peer) relationship and predict which link a packet takes from each.
- Explain why the NSFNET-to-commercial transition required **NAPs** and how a NAP differs operationally from a modern multilateral **IXP** fabric.
- Define a **tier-1 ISP** precisely (buys no transit, reaches the whole Internet via peers) and explain why the tier count is a *business* claim, not a protocol field.
- Trace a packet across an AS graph using the **valley-free** rule and identify which hops are provider-to-customer, which are peer-to-peer, and which are forbidden.
- Read a `traceroute` output, map the visible hops to ISPs via their reverse DNS, and infer where peering (a hop to a new AS) versus transit (a hop within the same backbone) is occurring.

## The Problem

You run `traceroute` from your home laptop in Berlin to `1.1.1.1` (Cloudflare) and see twelve hops. The first three are your home router, your DSLAM's BRAS, and `de.berlin.fra.telekom.net` — your access ISP, Deutsche Telekom. The middle hops march across `ae-2.r21.fra` and `ae-1.r04.ams` — Telekom's Frankfurt and Amsterdam core — then suddenly a hop reads `cloudflare.peer.ams-ix.net`. Why did the path stay inside Telekom for four hops and then jump to a different AS in one hop? Why does a traceroute to the same destination from a different laptop, on a competing access ISP, take an entirely different middle section — sometimes longer in hop count yet *faster* in latency? And why, when you accidentally traceroute to a host on a tiny regional ISP, does the path climb up to a tier-1 and back down rather than going "sideways" through a peer?

This is the symptom: the Internet's internal shape is invisible to the IP layer. IP has no "tier" field, no "this is a peering link" flag, no notion of NAP or IXP. The shape is imposed entirely by routing policy derived from business contracts. To reason about why a packet went the way it did — or why it is *not* going the shortest path — you have to know the anatomy the textbook sketches in Fig. 1-29: access ISPs, POPs, backbones, IXPs, tier-1s, and the transit/peering distinction behind it all.

## The Concept

### The edge: last-mile access and the POP

| Access method | Home device | ISP-side device | Medium | Typical rate |
|---|---|---|---|---|
| Dial-up | Modem | Modem bank | Twisted pair, voice band | ≤ 56 kbps (4 kHz channel) |
| DSL | DSL modem | **DSLAM** | Twisted pair, above voice | sub-Mbps to hundreds |
| Cable | Cable modem | **CMTS** | Coaxial / HFC plant | sub-Mbps to gigabit |
| FTTH | ONT | **OLT** | Optical fiber | 10–100 Mbps+ |

A home computer joins the Internet through an access ISP. Fig. 1-29 shows these wired access paths. The bitrate bottleneck is the "last mile"; the modem (modulator-demodulator) turns bits into analog signals that traverse the existing plant. Once digitization lands at the DSLAM/CMTS/OLT, everything downstream is digital packet switching. The point where customer traffic enters the ISP's routed network is the **POP** (Point of Presence) — a location, not a protocol, colocated with telephone central offices and cable headends.

### The backbone: long-distance fiber between POPs

An ISP's backbone is the set of long-distance transmission lines interconnecting the routers at its POPs in the cities it serves. The textbook traces the lineage: the ARPANET backbone used 56-kbps leased lines between IMPs (Interface Message Processors), each a specially modified Honeywell DDP-316 minicomputer with 12K words of core memory. NSFNET v1 also used 56-kbps lines but between LSI-11 "fuzzball" routers — the first TCP/IP WAN. NSFNET v2 leased 448-kbps fiber from MCI and ran IBM PC-RTs as routers; v2 was overwhelmed and upgraded to 1.5 Mbps (T1). In 1990 the nonprofit ANS took over and pushed the links to 45 Mbps (T3), forming **ANSNET**. Each jump was forced by demand outstripping the previous backbone's capacity — the same curve modern Tier-1s ride by adding 100G and 400G wavelengths.

A packet whose destination is served directly by the ISP is routed across the backbone and delivered. Any other packet must be *handed to another ISP* at a meeting point — and that meeting point is where the Internet's political economy lives.

### Peering vs. transit: the two ISP relationships

ISPs connect at **IXPs**, drawn vertically in Fig. 1-29 because networks overlap geographically. An IXP is a room full of routers — at least one per participating ISP — joined by a LAN (historically Ethernet/FDDI, today a switch fabric, often 100G/400G). Because the LAN is shared, any ISP's router can forward to any other's in a single L2 hop. Two relationships are brokered across that fabric:

- **Transit** (customer-to-provider, c2p): the smaller ISP *pays* the larger for the right to reach the rest of the Internet through it. The provider announces the customer's prefixes to its own peers/upstreams, and announces essentially the *full* routing table down to its customer. This is how a regional ISP reaches the whole Internet without peering with everyone.
- **Peering** (peer-to-peer, p2p): two roughly equal networks agree to exchange traffic between *their own customers only* — "your users talk to my users, free of charge." Each peer announces only its own customer prefixes to the other, not the full table. This is settlement-free and the dominant cost-saving arrangement in the modern Internet.

The paradox the textbook notes: ISPs that publicly compete for customers privately cooperate on peering. Peering is a business deal, usually governed by a contract with balance conditions (similar geographic scope, similar traffic ratios, no congestion). When those conditions are violated, peering turns into paid transit or is cut — the "peering disputes" that occasionally make a large content network briefly unreachable.

### NAPs: the government exit strategy

NSF could not fund networking forever, and its charter forbade commercial use. To privatize the backbone without stranding the regional networks, NSF funded four **NAPs** (Network Access Points) in 1994 and awarded the operation contracts:

| NAP | Operator | City |
|---|---|---|
| PacBell NAP | Pacific Bell | San Francisco Bay Area |
| Ameritech NAP | Ameritech | Chicago |
| MAE-East | MFS | Washington, D.C. (MFS later WorldCom) |
| Sprint NAP | Sprint | New York City (Pennsauken, NJ) |

Any operator that wanted to sell backbone service to NSF's regional networks had to connect to *all four* NAPs. This guaranteed that a packet originating on any regional network had a choice of backbone carriers — and the carriers had to compete on price and service. The single-default-backbone era ended; commercial competition took its place. A NAP is functionally the ancestor of the modern IXP: a shared fabric where networks exchange traffic. The terminology faded because the model was generalized — today an IXP runs the same fabric (a big switched LAN) but membership is multilateral and global, and the term NAP survives mainly in history and in the names of a handful of legacy fabrics

### The tier hierarchy: who is really at the top

At the top sit a small handful of companies running large international backbones — the textbook names AT&T and Sprint; the modern list includes NTT, Lumen (formerly CenturyLink/Level 3), Telia (Arelion), Tata Communications, GTT, and Cogent. These are **tier-1 ISPs**. The defining trait is *negative*: a tier-1 buys transit from nobody and reaches the entire Internet solely through its peering relationships. Because every other network, directly or indirectly, must transit a tier-1 to reach the whole Internet, the tier-1s form the de facto backbone of the Internet.

The catch is that "tier-1" is a *business* claim, not a protocol field. There is no IANA registry of tiers, no BGP attribute that says "I am tier-1." In practice a network is tier-1 if it has a sufficiently dense set of settlement-free peers among the other top networks that it has no paid upstream. Cogent has famously been in periodic disputes where peers say it does not meet their balance conditions and downgrade the relationship to paid transit — at which point the "tier-1" status becomes arguable. The numbered hierarchy below — tier-2 (buys transit, peers with some), tier-3 (mostly buys transit) — is even looser; engineers use it as shorthand for "how far up the food chain you go before someone carries your traffic for free."

### Valley-free routing: why packets don't take the shortest path

The path a packet takes through the Internet is determined by BGP routing policy, and that policy is shaped by the c2p / p2p relationships above. The dominant model, due to Gao (2001), is the **valley-free** rule: an AS path is valid only if it consists of

1. zero or more **up** steps (customer → provider), then
2. zero or one **across** steps (peer ↔ peer), then
3. zero or more **down** steps (provider → customer).

It can go *up*, then *across at most once*, then *down* — forming an inverted "V" (a peak, with no valley). A "down then up" sequence is forbidden, because the provider that carried the downstream traffic upward would be forwarding traffic for which nobody paid. This is why traceroutes to a small remote ISP climb to a tier-1 and descend, rather than crisscrossing sideways: the p2p edges only carry traffic between their *own* customers, so a transit hop has to bracket any peering hop.

Worked example. Suppose an AS graph has the edges (with direction `cust→prov` meaning "customer buys transit from provider", and `peer` meaning p2p):

```
A (access) --cust→prov--> R (regional) --cust→prov--> T1 (tier-1)
A (access) --peer--> B (access, at IXP) --cust→prov--> T2 (tier-1)
T1 --peer--> T2 --cust→prov--> C (content)
```

For a packet from A to C, valid AS paths under valley-free are:

| Candidate path | Edges | Valid? | Why |
|---|---|---|---|
| A → T1 → T2 → C | up, peer, down | Yes | peak at T1→T2 |
| A → B → T2 → C | peer, up, down | No | goes down/across then UP — valley |
| A → T1 → C | up, (no edge to C) | N/A | no edge T1→C exists |

So the route is forced up to a tier-1 and across the T1↔T2 peering edge, never the tempting shortcut A→B. This is the operational reason the "shortest" path is rarely the one taken — the Internet optimizes for who-pays-for-what, not geography. The lineage of those tier-1 backbones is the textbook's: 56 kbps (ARPANET IMPs, NSFNET fuzzballs) → 448 kbps → 1.5 Mbps T1 → 45 Mbps T3 (ANSNET) → today's 100G/400G wavelengths, with a DFZ routing table that grew from a few thousand prefixes to ~950,000 IPv4 + ~200,000 IPv6. `code/main.py` encodes the valley-free rule and prints the surviving path; `assets/internet-anatomy-backbones-naps-ixps.svg` pictures the same topology.

### Reading traceroute as anatomy

`traceroute` (and `mtr`, `tracepath`) exposes the AS path indirectly via increasing the IP **TTL** field (RFC 1812, §5.3.1) from 1 upward; each router that decrements TTL to zero emits **ICMP Time Exceeded** (type 11, code 0) back to the source. The source times each round trip and prints the responding router, which is usually named in reverse DNS encoding the city (`fra` = Frankfurt, `ams` = Amsterdam), the interface role (`ae-2.r21` = aggregated Ethernet on router 21), and the operator. Mapping those domain fragments to AS numbers via `whois -h whois.cymru.com` reveals the valley-free shape: hops within one AS are transit *inside* a backbone; a hop to a new AS at the *same* city (e.g., Telekom Frankfurt → Cloudflare Frankfurt) is IXP peering; a hop to a new AS at a *distant* city is paid transit at the edge of a backbone. A sudden jump of ASNs near the destination is the textbook's "two example paths across ISPs" rendered into visible hops.

## Build It

1. Open `code/main.py`. It models a small Internet as an AS graph with edges labeled `c2p` (transit) or `p2p` (peering), and implements `valley_free_paths()` to enumerate all policy-valid AS paths from a source to a destination.
2. Run `python3 code/main.py` with the bundled demo: it traces a packet from an access ISP up through a regional provider to a tier-1, across a peering edge at an "IXP", and down to a content network. Confirm the printed path is *up, across, down* — and that the tempting shortcut across a different peer is rejected with the reason printed.
3. Read the `traceroute_decode()` helper. Hand it a list of reverse-DNS hop names and it splits each into `(city, role, operator)` triples and marks where a new ASN appears — the anatomy you'd read in a real `traceroute`.
4. Edit the `AS_GRAPH` dict: turn the `T1 → T2` edge from `p2p` to `c2p` (one buys transit from the other) and rerun. Watch the set of valid paths change because the single allowed peer-edge moved.
5. Add a third tier-1 `T3` and a peering triangle T1–T2–T3. Find a source/destination pair where two distinct valid valley-free paths coexist; the model prints both, just as BGP would receive equal-preference routes and pick by tie-break (`AS_PATH` length, `LOCAL_PREF`, router-ID).

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Tell peering from transit | In the printed AS path, mark each hop `up`, `across`, or `down` | Peering hops flatten to one `across` step between customers; transit hops climb or descend across ownership |
| Predict the valley-free path | Candidate path string from `code/main.py` | Climb → at most one peer edge → descend; never descends and then climbs |
| Read a real traceroute | First hop in customer AS, later hop in a different AS in the same city, latency flat | The new-AS hop at constant RTT is the IXP peering handoff, not paid transit |
| Spot a tier-1 in the path | ASN resolves (via `whois`) to AT&T, NTT, Lumen, Telia, Tata, Cogent | The ascent ends there; the packet crosses _peer_ links among tier-1s rather than buying transit upward |
| Diagnose a detour | Traceroute shows up-down through a tier-1 when a near peer exists | The near peer does not announce the destination's prefix (not its customer), so the valley-free rule forbids the shortcut |
| Reason about a NAP | Draw the 1994 four-NAP topology (SF, Chicago, DC, NYC/NJ) and the contract rule | Every backbone had to connect to all four NAPs, so any regional network could reach any backbone |

## Ship It

Produce one artifact under `outputs/` named `prompt-internet-anatomy-backbones-naps-and-isps.md`:

- A captured `traceroute -n` from your machine to a content host (e.g., `1.1.1.1`), annotated hop by hop with: city, operator, ASN (via `whois -h v4.whois.cymru.com`), and a label `access` / `transit-up` / `peering` / `transit-down` / `destination`.
- A small AS-graph sketch (reuse `code/main.py`'s edge list, edited to match your actual observed path) and the computed valley-free path between your access ISP and the destination's AS.
- A one-paragraph verdict: which hops are inside your ISP's backbone, which hop is the IXP peering handoff, and whether the path is policy-bounded rather than shortest.

Start from the printed output of `code/main.py` and annotate it with the trace you actually captured.

## Exercises

1. In 1994 NSF required every commercial backbone to connect to all four NAPs (PacBell/SF, Ameritech/Chicago, MFS/DC, Sprint/NYC). Suppose a fifth backbone connected to only three of them. Which pair of regional networks could *not* exchange traffic, and why does the four-NAP rule prevent that?
2. Your (German) traceroute to `91.198.174.192` (Wikimedia) shows `de.wikimedia.ams-ix.net` halfway through. Explain why this is a peering hop and not paid transit, and what reverse-DNS and ASN evidence you would require to be sure.
3. Using `code/main.py`, construct a topology where AS A peers with B at an IXP, B buys transit from tier-1 T1, and the destination lives on T2 (another tier-1 that peers with T1). Write the *only* valley-free path from A to the destination's host, labeling every edge. Then change the A–B edge from `p2p` to `c2p` (B becomes A's transit provider) — does the path set change?
4. A tier-1's marketing department claims "we are tier-1 because we have the most routers." Give the precise definition of tier-1 and refute them: which BGP-level and contract-level facts would you check, and which would be irrelevant?
5. Consider the modern table rates: a backbone link went from 1.5 Mbps (ANSNET, 1990) to 400 Gbps (2024). How many times has that multiplied, and roughly how many 56-kbps ARPANET lines does one modern wavelength equal? Comment on why the textbook's "voice-band 56 kbps was the best money could buy" claim is not a standing truth about technology but about a moment in time.
6. Two networks are in a peering dispute: Network P says Network Q's traffic ratio drifted to 6:1 and wants to charge transit; Q disputes the measurement. Explain how a multilateral IXP switch fabric lets either side unilaterally de-peer (shut the BGP session), and trace the valley-free consequence for two hosts on P and Q respectively: where must their traffic now go?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| POP (Point of Presence) | "an ISP node" | The physical location where customer packets enter the ISP's routed network; colocated with telco/cable headends, holds access concentrators and edge routers |
| Backbone | "the big pipes" | The set of long-distance transmission lines interconnecting an ISP's POPs and the core routers between them |
| IXP (Internet eXchange Point) | "a meeting room" | A switched LAN in a facility where participating ISPs each place a router and forward packets L2-to-L2; the broker of modern peering |
| NAP (Network Access Point) | "old word for IXP" | The four NSF-funded fabric points (SF, Chicago, DC, NYC/NJ) that privatized NSFNET in 1994; the historical model the modern IXP generalizes |
| Peering (p2p) | "free interconnect" | Settlement-free exchange of traffic _only between each network's own customers_; each side advertises only its customer prefixes to the other |
| Transit (c2p) | "buying upstream" | A paid customer-to-provider relationship in which the provider reaches the rest of the Internet (announces the full DFZ table) for the customer |
| Tier-1 ISP | "the top ISP" | A network that buys transit from nobody and reaches the whole Internet via settlement-free peering with the other top networks; a business claim, not a protocol field |
| DSLAM | "the DSL box" | Digital Subscriber Line Access Multiplexer: the ISP-side device that terminates DSL signals and converts to digital packets |
| CMTS | "the cable thing" | Cable Modem Termination System: the headend counterpart to a cable modem on a hybrid fiber-coax plant |
| Valley-free | "the up-across-down rule" | A BGP-level policy constraint (Gao 2001): valid AS paths climb customers-to-providers, cross at most one peer edge, then descend providers-to-customers — never down-then-up |
| ANSNET / NSFNET | "first IP backbone" | The NSF-funded TCP/IP WAN (fuzzball routers, then 448 kbps/1.5 Mbps/45 Mpbs MCI fiber) that ANS operated and privatized via the NAPs in 1994 |
| DFZ (Default-Free Zone) | "the full table" | The set of routers carrying a "default-free" full BGP table (~950k IPv4 + ~200k IPv6 prefixes); tier-1 core routers live here |

## Further Reading

- **Lixin Gao**, "On Inferring Autonomous System Relationships in the Internet," *IEEE/ACM Transactions on Networking*, 9(6), 2001 — the valley-free / up-across-down model.
- **Craig Labovitz et al.**, "Internet Inter-domain Traffic," ACM SIGCOMM 2011 — empirical breakdown of where traffic crosses peering vs transit.
- **B. Carpenter, ed.**, **RFC 1958** — Architectural Principles of the Internet (the "no single backbone" philosophy statement).
- **Y. Rekhter & T. Li**, **RFC 4271** — BGP-4, the protocol that carries the AS-path whose shape valley-free policy constrains.
- **G. Huston**, **RFC 7226** — A Survey of the Characteristics of the Default-Free Zone (DFZ table growth).
- **CAIDA AS Relationships dataset** — the operational c2p/p2p classification derived from Gao's inference.
- **Metz, "Interconnecting ISP Networks," *IEEE Internet Computing*, 2001** — the textbook's cited source on the peering paradox.
- **PeeringDB** (peeringdb.com) — the public registry of IXP fabric members and peering policy per network.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Section 1.5.1 "The Internet" — the source chapter for this lesson, including the ARPANET/NSFNET/ANSNET history and the four-NAP privatization.