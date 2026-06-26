# Who's Who in the Internet Standards World to Architecture Review Lab

> The Internet runs on documents, not committees in suits. Every protocol you trace — TCP's three-way handshake (RFC 9293), IPv4 headers (RFC 791), DNS messages (RFC 1035), HTTP/1.1 (RFC 9110) — traces back to a numbered **Request for Comments (RFC)** produced by the **IETF** under the **IAB**, governed by the **Internet Society (ISOC)**. David Clark's 1992 motto, "We reject kings, presidents, and voting. We believe in rough consensus and running code," is the operating principle: an idea becomes a **Proposed Standard** only after an RFC plus community interest, and historically advanced to **Draft Standard** only after two independent interoperable implementations tested for at least four months (the three-tier ladder of RFC 2026; collapsed to two levels by RFC 6410 in 2011). RFCs are immutable once published — you never edit RFC 791, you publish a new RFC that **obsoletes** or **updates** it. This lab teaches you to read any RFC's metadata header (number, category, Obsoletes/Updates/Obsoleted-By) so that when a capture disagrees with a spec, you know *which* spec, *which version*, and *whether it is still authoritative*.

**Type:** Build
**Languages:** Diagrams, standards, Python, Markdown
**Prerequisites:** Phase 1 lessons on layering, protocols, and the ITU-T/ISO standards bodies (1.6.1, 1.6.2)
**Time:** ~90 minutes

## Learning Objectives

- Map each Internet standards body (ISOC, IAB, IETF, IRTF, IESG, IANA, W3C) to its concrete function and to the artifact it produces.
- Read an RFC's status block — number, category (Standards Track / Informational / Experimental / BCP / Historic), and Obsoletes/Updates relationships — and decide whether it is the authoritative reference for a given protocol field.
- Trace the standards-track ladder from Internet-Draft to Proposed Standard to Internet Standard, including the two-implementation interoperability requirement.
- Resolve an "RFC chain" — given a starting RFC, follow Obsoletes/Updates pointers to find the document that actually governs the wire format you captured.
- Use `code/main.py` to parse RFC metadata and compute the currently authoritative RFC for a protocol, the way a troubleshooting engineer must before quoting a spec.

## The Problem

You are debugging a TLS handshake a security scanner flagged. The scanner cites "RFC 5246, Section 7.4.1.2." Your capture shows a `supported_versions` extension the scanner never mentions. You read RFC 5246 cover to cover and the extension is simply not there. Two hours later you discover RFC 5246 (TLS 1.2) was **obsoleted by RFC 8446 (TLS 1.3)** in August 2018, and the extension lives in the newer document. You quoted a dead spec.

This is the daily failure mode of Internet standards: the spec is never a single PDF. It is a *graph* of numbered, immutable documents linked by Obsoletes, Updates, and Obsoleted-By relationships, each carrying a maturity status (Proposed Standard, Internet Standard, Experimental, Historic). An engineer who cannot read that graph quotes the wrong field name, the wrong default timer, or a security mitigation removed three RFCs ago. This lesson builds the literacy and a small tool to stop that.

## The Concept

The Internet has no government and no treaty body. Its standards come from a deliberately informal, bottom-up process whose authority is running code and broad adoption, not a ministry. The diagram in [`assets/who-s-who-in-the-internet-standards-world-to-architecture-review-lab.svg`](../assets/who-s-who-in-the-internet-standards-world-to-architecture-review-lab.svg) shows the organizational tree and the document lifecycle side by side.

### The organizational tree

When the ARPANET was set up, the DoD created an informal oversight committee. In 1983 it became the **IAB** (Internet Activities Board, later renamed Internet Architecture Board). By 1989 the Internet had outgrown ten researchers thrashing out routing algorithms over email, and the IAB was reorganized into the structure still in use:

| Body | Full name | Role | Produces |
|---|---|---|---|
| ISOC | Internet Society | Legal/financial umbrella; elects trustees who appoint the IAB | Governance, funding |
| IAB | Internet Architecture Board | Long-range architecture oversight, appeals, liaison | Architectural guidance |
| IETF | Internet Engineering Task Force | Short-term engineering; >100 working groups grouped into areas | RFCs (the standards) |
| IESG | Internet Engineering Steering Group | Area directors who approve documents for publication | Last-call decisions |
| IRTF | Internet Research Task Force | Long-term research (subsidiary to IAB) | Research RFCs |
| IANA | Internet Assigned Numbers Authority | Allocates port numbers, protocol numbers, IP blocks | Number registries |
| W3C | World Wide Web Consortium | Web-layer standards, led by Tim Berners-Lee, founded 1994 | W3C Recommendations (HTML, etc.) |

The split is deliberate: the **IRTF** chases ideas that may not pan out (new congestion control, post-quantum key exchange), while the **IETF** ships engineering people deploy this quarter. The IETF has no membership and no dues — anyone can join a working group mailing list. There is no vote; the chair declares "rough consensus" by reading the room and the list.

### What an RFC actually is

A **Request for Comments** is an immutable technical document, numbered in strict chronological order of publication (RFC 1 dates to 1969; the count is now well past 9000) and archived at `www.ietf.org/rfc`. Two properties drive everything:

1. **Immutability.** Once published, an RFC's text never changes — there is no RFC 791 revision 2. To fix or extend it you publish a *new* RFC pointing back at the old one.
2. **Status metadata.** Every RFC carries a header block. The fields you must read:

| Field | Example | Meaning |
|---|---|---|
| Number | RFC 9293 | Permanent identifier |
| Category | Standards Track | Maturity intent (see ladder below) |
| Obsoletes | 793, 879, 6093, 6528 | This RFC fully replaces those; they are now Historic in effect |
| Updates | 1011, 1122 | This RFC amends parts of those, which remain otherwise valid |
| Obsoleted by | (empty) | If present, this RFC is dead; follow the pointer |
| ISSN | 2070-1721 | RFC series identifier |

RFC 9293 (TCP, 2022) obsoletes RFC 793 from 1981 plus four patch RFCs, folding 40 years of errata into one document. Reach for RFC 793 and you are reading a superseded spec.

### The standards-track ladder

A proposal does not become a standard by fiat. The maturity ladder from RFC 2026 (1996):

```text
Internet-Draft  ──►  Proposed Standard  ──►  Draft Standard  ──►  Internet Standard
 (work in       │    (RFC + community     │   (2 independent      │  (mature, widely
  progress,     │     interest, stable    │    interoperable      │   deployed; gets an
  expires in    │     spec)               │    implementations,   │   STD number)
  6 months)     │                         │    ≥4 months testing) │
```

The middle rung is the famous one: to advance to **Draft Standard**, a working implementation had to be **rigorously tested by at least two independent sites for at least four months**. This is "running code" enforced as policy — you cannot standardize a protocol nobody has built twice. In 2011, **RFC 6410** simplified the ladder to two levels because almost nothing was being promoted past Proposed. Much of TCP/IP sat at Proposed Standard for decades.

Not every RFC is on the standards track. Categories you meet:

| Category | Purpose | Example |
|---|---|---|
| Standards Track | Intended to become a standard | RFC 9293 (TCP) |
| Informational | Documents an idea, no standardization claim | RFC 1796 ("Not All RFCs Are Standards") |
| Experimental | Try it, gather data | many early QUIC drafts |
| Best Current Practice (BCP) | Operational/process rules | RFC 2026 (the process itself, BCP 9) |
| Historic | Obsolete, kept for the record | RFC 793 after RFC 9293 |

### Reading an RFC chain — worked example

A capture shows an HTTP request and you want the authoritative grammar for the request line. Naively you grab RFC 2616 (HTTP/1.1, 1999). The chain:

```text
RFC 2616 (1999) ─obsoleted by─► RFC 7230–7235 (2014, split into 6 docs)
                                    └─obsoleted by─► RFC 9112 (HTTP/1.1)  ◄── authoritative
```

The authoritative request-line grammar lives in **RFC 9112 §3**, not RFC 2616. `code/main.py` walks this chain: give it a starting RFC, it follows `Obsoleted by` edges to the document with no successor, reports that as the live spec, and warns if your start is dead.

### Why "rough consensus and running code" matters operationally

The motto predicts behavior you will observe in the field. Because adoption (running code), not a committee vote, decides what wins, *deployed* reality can diverge from the *latest* RFC. TLS 1.3 (RFC 8446) was final in 2018, yet middleboxes that hard-coded TLS 1.2 assumptions broke it, forcing the working group to disguise 1.3 as 1.2 on the wire. When your capture disagrees with the newest RFC, the cause is often that the *installed base* runs older code — the tension the two-implementation rule exists to surface.

## Build It

1. Read `code/main.py`. It models a registry of real RFCs with `category`, `obsoletes`, and `obsoleted_by` fields.
2. Run `python3 main.py`. Watch it resolve the authoritative RFC for TCP, HTTP/1.1, and TLS by walking the Obsoletes chain.
3. Add RFC 8200 (IPv6), which obsoletes RFC 2460, to the `REGISTRY` dictionary and re-run to confirm the resolver picks it up.
4. Feed the resolver a dead RFC number (e.g. 793) and confirm it warns you and redirects to the live document.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Identify the governing body | The artifact type (RFC vs W3C Recommendation vs ITU-T Rec.) | You name IETF for an RFC, W3C for HTML, ITU-T for H.264 — and explain why |
| Find the authoritative spec | RFC header: Category + Obsoleted-by chain | You quote the live RFC (e.g. 9293 for TCP), never a silently superseded one |
| Judge maturity | Category field + STD number | You distinguish a Proposed Standard from an Informational or Experimental RFC |
| Resolve a spec disagreement | Capture vs RFC text + chain resolution | You can say "the capture follows RFC 9112, the scanner cited obsolete RFC 2616" |

## Ship It

Produce one reusable artifact under `outputs/`:

- An **RFC-chain resolver cheat sheet** mapping the protocols you use most (TCP, IP, DNS, HTTP, TLS) to their *currently authoritative* RFC numbers and obsoleted predecessors.
- A **standards-body decision card**: given an artifact, which body owns it and where the registry lives.

Start with [`outputs/prompt-who-s-who-in-the-internet-standards-world-to-architecture-review-lab.md`](../outputs/prompt-who-s-who-in-the-internet-standards-world-to-architecture-review-lab.md).

## Exercises

1. A vendor's security audit cites "RFC 5246 §7.4.1" for a TLS cipher requirement. Using the Obsoletes graph, find the document that actually governs TLS today and name the specific RFC that killed 5246.
2. You capture a TCP segment with a Selective Acknowledgment (SACK) option. RFC 793 does not mention SACK. Name the RFC that *updates* TCP to add SACK, and explain why it "updates" rather than "obsoletes" 793.
3. Classify each of these by governing body and artifact type: HTML5, the IPv6 header, X.509 certificates, the H.264 codec, Bluetooth. (Hint: not all of them are IETF.)
4. The IETF requires two independent interoperable implementations to advance to Draft Standard. Argue why this rule produced more robust protocols than ISO's pure committee-draft voting process described in section 1.6.2.
5. RFC 6410 (2011) collapsed the three-level ladder to two. Explain what operational problem it was solving — why almost no protocol was reaching the old "Internet Standard" top tier.
6. Run `code/main.py`, then add RFC 1035 (DNS) and a hypothetical successor that obsoletes it. Confirm the resolver redirects and prints the Historic status of 1035.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| RFC | "an internet standard" | A numbered, immutable document — most RFCs are *not* standards (Informational, Experimental, Historic all exist) |
| Obsoletes | "references the old one" | This RFC *replaces* the named RFC entirely; the old one becomes effectively Historic |
| Updates | "obsoletes" | This RFC *amends part* of the named RFC, which otherwise stays valid — a surgical patch, not a replacement |
| Proposed Standard | "final standard" | The *entry* rung of the standards ladder; most deployed protocols never formally climbed higher |
| Rough consensus | "majority vote" | The chair's judgment that objections are addressed — there is explicitly *no* vote |
| IETF | "the people who run the internet" | A volunteer engineering body with no membership, dues, or vote, producing RFCs via working groups |
| IAB | "the same as IETF" | The architecture-oversight board *above* the IETF; handles appeals and long-range direction, not document authorship |
| Internet-Draft | "a small RFC" | A working document with no standing that *expires in six months* if not advanced |

## Further Reading

- RFC 2026 — *The Internet Standards Process, Revision 3* (BCP 9), the canonical description of the ladder.
- RFC 6410 — *Reducing the Standards Track to Two Maturity Levels* (2011).
- RFC 1796 — *Not All RFCs Are Standards* (the classic warning).
- RFC 9293 — *Transmission Control Protocol* (2022), obsoleting RFC 793 and four others — read the header block.
- RFC 8446 — *The Transport Layer Security (TLS) Protocol Version 1.3*, obsoleting RFC 5246.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Section 1.6.3.
- The IETF Tao — *Hitchhiker's Guide to the IETF*.
