# RFID and Sensor Networks to Who's Who in the International Standards World

> RFID turns everyday objects into network endpoints with no battery: a passive UHF tag in the 902–928 MHz band harvests the reader's RF energy and replies by **backscatter** — flipping the impedance of its antenna so it reflects or absorbs the carrier, encoding bits at distances of several meters. HF RFID at 13.56 MHz instead uses near-field **inductive coupling**, giving a sub-meter range that protects passports and contactless cards. When many tags sit in one reader's field their replies collide, so EPCglobal Gen2 uses a **slotted-ALOHA** anti-collision protocol: the reader broadcasts a `Query` with a slot-count parameter `Q`, each tag loads a random value into a slot counter, and only tags reaching slot 0 backscatter a 16-bit `RN16` handle. Sensor networks go one step further — battery-powered nodes self-organize into a **multihop** mesh (IEEE 802.15.4 / ZigBee) to relay readings to a collection sink. Above the wire sits the political layer: **de jure** bodies (ITU-T, ISO, IEEE 802, IETF) versus **de facto** standards (HTTP, Bluetooth) that "just happened." Knowing whether you are reading an ITU-T `H.264` Recommendation, an ISO `IS`, an IEEE `802.15.4` spec, or an IETF `RFC` tells you who owns the document, how it changes, and how binding it is.

**Type:** Learn
**Languages:** Diagrams, standards
**Prerequisites:** Phase 1 lessons on wireless LANs (802.11), the OSI/TCP-IP layering model, and framing
**Time:** ~75 minutes

## Learning Objectives

- Distinguish UHF backscatter RFID (902–928 MHz, ~several meters) from HF inductive RFID (13.56 MHz, ~1 m) by physical mechanism, range, and typical application.
- Trace one round of the EPC Gen2 slotted-ALOHA `Query` / `RN16` / `ACK` / `EPC` exchange and compute the expected number of singulated tags for a given slot count `Q`.
- Explain why a sensor network uses a multihop mesh instead of single-hop, and what failure modes (energy depletion, partition) that introduces.
- Map a standard's identifier (`RFC 9293`, `ISO/IEC 18000-63`, `IEEE 802.15.4`, ITU-T `X.509`) to the body that owns it and its document lifecycle (Internet-Draft → RFC; CD → DIS → IS).
- Classify a real-world standard as de facto or de jure and predict how that affects interoperability and change control.

## The Problem

A logistics warehouse installs a UHF RFID portal at the loading dock. In testing with one tagged carton everything reads at 4 meters. In production a forklift carries 60 tagged cartons through the portal at once and the read rate collapses to 70% — a dozen cartons are silently missed and the inventory database drifts out of sync with reality.

Nothing is "broken." There is no error log, no crash. The symptom is *missing reads*, and the engineer has to reduce that vague symptom to a layer-specific cause: tag-to-tag **collisions** in the reader's RF field because the anti-collision `Q` parameter was tuned for a handful of tags, not sixty. Fixing it means understanding the singulation protocol, not buying a bigger antenna.

The second half of this lesson is the flip side: when you look up *how* Gen2 singulation is supposed to work, the answer lives in `EPCglobal Gen2` / `ISO/IEC 18000-63`, the radio band is governed by `ITU-R`, and the sensor-mesh sibling lives in `IEEE 802.15.4`. Knowing **who owns which document** is itself an operational skill.

## The Concept

The source is *Computer Networks* (Tanenbaum), Chapter 1 — RFID and sensor networks (the example-networks section) and the "Who's Who" standardization sections. See [`code/main.py`](../code/main.py) for a runnable Gen2 singulation simulator and a standards classifier, and the diagram in [`assets/rfid-and-sensor-networks-to-who-s-who-in-the-international-standards-w.svg`](../assets/rfid-and-sensor-networks-to-who-s-who-in-the-international-standards-w.svg) for the field-and-mesh topology.

### Passive vs active, UHF vs HF

Most RFID tags have **neither a plug nor a battery**. All operating energy is delivered as radio waves by the reader — *passive* RFID. The rarer *active* tag carries its own power source and can initiate or extend range.

| Property | UHF RFID | HF RFID | LF RFID |
|---|---|---|---|
| Frequency | 902–928 MHz (US ISM) | 13.56 MHz | 125–134 kHz |
| Coupling mechanism | Backscatter (far field) | Inductive (near field) | Inductive (near field) |
| Typical range | Several meters | ≤ 1 meter | A few cm |
| Typical use | Pallets, supply chain, some driver licenses | Passports, credit cards, transit cards | Animal/pet implants, immobilizers |
| Standard | EPC Gen2 / ISO/IEC 18000-63 | ISO/IEC 14443, ISO/IEC 15693 | ISO/IEC 11784/11785 |

The band assignment is not arbitrary: the 902–928 MHz and 2.4–2.5 GHz **ISM bands are defined by ITU-R** (the Radiocommunications Sector), which is why the *exact* US UHF band differs from Europe's 865–868 MHz — a tag printed for one region can be unreadable in another.

### Backscatter: how a battery-less tag "transmits"

A passive UHF tag does not generate its own carrier. The reader emits a continuous wave; the tag encodes bits by **switching the impedance** of its antenna between two states — matched (absorbs energy) and mismatched (reflects energy). The reflected signal is the **backscatter** the reader demodulates. Because the link budget is dominated by the round-trip path loss (energy out to the tag *and* the weak reflection back), UHF range is a few meters while HF inductive coupling — where the reader and tag coils share a magnetic field — falls off far faster and is limited to about a meter.

### The collision problem and slotted-ALOHA singulation

When several tags are energized at once, a tag that simply replies the instant it hears the reader will collide with its neighbors. The fix mirrors 802.11's randomized backoff: **each tag waits a random slot before answering**, so the reader can isolate ("singulate") one tag at a time.

EPC Gen2 (ISO/IEC 18000-63) makes this concrete with a frame-slotted ALOHA round:

1. Reader broadcasts `Query` carrying a parameter `Q` (0–15). The frame has `2^Q` slots.
2. Each tag picks a random slot counter in `[0, 2^Q − 1]`.
3. On each `QueryRep`, every tag decrements its counter. A tag whose counter hits **0** backscatters a 16-bit random handle `RN16`.
4. **One tag in the slot (singleton)** → reader replies `ACK(RN16)`; the tag sends its `EPC` (a 96-bit Electronic Product Code identifier plus a CRC-16/PC word).
5. **Zero tags** → idle slot (wasted time). **Two or more** → collision; those tags get no `ACK` and re-roll on a later round.

Worked example: with `n` tags and `2^Q` slots, the probability a given slot holds exactly one tag is `n·(1/L)·(1−1/L)^(n−1)` where `L = 2^Q`. The expected number of *successful* singletons is `n·(1−1/L)^(n−1)`. For `n = 60` tags and `Q = 4` (`L = 16`), expected singletons per round ≈ `60·(15/16)^59 ≈ 60·0.022 ≈ 1.3` — almost every slot collides, which is exactly the warehouse failure. Raising to `Q = 6` (`L = 64`) gives `60·(63/64)^59 ≈ 60·0.395 ≈ 23.7` singletons per round — far healthier. The Gen2 `Q`-adjust algorithm grows `Q` after collisions and shrinks it after idle slots to track the population. `code/main.py` runs this simulation and prints reads-per-round versus `Q`.

### From RFID to sensor networks: the multihop mesh

A sensor node is a small battery-powered computer (often key-fob sized) with temperature, vibration, or other sensors, scattered across the area to be monitored — bird habitats, volcanoes, refrigerated cargo. Unlike a passive tag, it has limited stored energy, so it cannot afford a powerful radio that reaches the sink directly. Instead nodes **self-organize and relay for each other**: a reading hops node-to-node toward the data-collection point. This is a **multihop network** (IEEE 802.15.4 PHY/MAC, with ZigBee or 6LoWPAN above it).

Multihop buys range and saves energy per hop, but introduces new failure modes:

| Failure mode | Symptom | Evidence to collect |
|---|---|---|
| Energy depletion of a relay | A whole branch of the tree goes silent | Per-node battery telemetry; last-heard timestamps |
| Network partition | Sink sees readings from only one cluster | Routing/parent tables; hop-count to sink |
| Hidden-terminal collisions | Intermittent loss near a busy relay | MAC retry counters; CSMA-CA backoff stats |
| Duty-cycle desync | High latency, bursty delivery | Radio wake schedule vs. observed RX windows |

### Who's Who: de facto vs de jure

Standards split into two families. **De facto** ("from the fact") standards just happened: HTTP began as Tim Berners-Lee's browser protocol at CERN; Bluetooth began inside Ericsson. **De jure** ("by law") standards are ratified by a formal body. Successful de facto standards often get *adopted* into de jure ones — HTTP was picked up by the IETF.

| Body | Type | Owns / examples | Document lifecycle |
|---|---|---|---|
| **ITU-T** (was CCITT) | Treaty (UN agency) | Telephony, `H.264`, `X.509`, DSL (Study Group 15) | Recommendation, adopted by member governments |
| **ITU-R** | Treaty | Radio spectrum, ISM band allocations | Recommendation |
| **ISO** (with IEC as JTC1) | Voluntary national bodies | OSI model, `ISO/IEC 18000-63`, 17,000+ standards | CD → DIS → IS |
| **IEEE 802** | Professional society | `802.3` Ethernet, `802.11` WiFi, `802.15` PAN (Bluetooth/ZigBee) | Working-group draft → standard |
| **IETF** (under IAB / ISOC) | Open, "rough consensus and running code" | TCP/IP, `RFC 9293`, routing, security | Internet-Draft → RFC |

Two facts worth memorizing: IEEE 802's success rate is uneven — an `802.x` number is no guarantee (802.4 token bus, 802.14 cable modems both died), but `802.3` and `802.11` reshaped the industry. And ISO's true name is the *International Organization for Standardization* — "ISO" is not an acronym but a deliberate language-neutral name. `code/main.py` maps an identifier string to its owning body and type.

## Build It

1. Read [`code/main.py`](../code/main.py). It has two parts: a frame-slotted-ALOHA Gen2 singulation simulator, and a standards-identifier classifier.
2. Run `python3 code/main.py`. Watch the simulator print, for a fixed tag population, how reads-per-round change as `Q` rises from 2 to 8 — and find the `Q` that maximizes throughput.
3. Read the standards classifier output: feed it `802.15.4`, `RFC 9293`, `ISO/IEC 18000-63`, `H.264` and confirm it names the right body and de facto/de jure type.
4. Sketch the warehouse scenario on the SVG topology: 60 tags in one reader field, mesh of sensor nodes relaying to a sink.
5. Change `NUM_TAGS` to 60 and confirm `Q = 4` collapses while `Q = 6` recovers — reproduce the worked example.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Diagnose low RFID read rate | Reads-per-round vs. `Q`; collision/idle slot ratio | You can show `Q` was undersized for the tag population and predict the corrected value |
| Pick the right RFID flavor | Frequency band, coupling mechanism, range budget | UHF chosen for meters-of-range pallets; HF for short-range secure cards — with the band justified |
| Triage a silent sensor branch | Per-node last-heard time, battery telemetry, hop counts | You localize the dead relay or the partition rather than blaming the sink |
| Identify a standard's owner | The identifier prefix (`RFC`, `ISO/IEC`, `802.`, `H.`/`X.`) | You name the body, its type, and how the document changes |

## Ship It

Produce one artifact under `outputs/`:

- A one-page RFID singulation runbook: symptom (missed reads) → `Q` tuning math → fix.
- A standards cheat-sheet table mapping identifier prefixes to bodies, types, and lifecycles.
- The annotated SVG topology with the collision and multihop failure modes labeled.

Start from the simulator output and the classifier table in [`code/main.py`](../code/main.py).

## Exercises

1. A driver pushes 120 tagged cartons through a UHF portal. The reader is configured with `Q = 4`. Using the singleton formula `n·(1−1/L)^(n−1)`, estimate singletons per round, then find the smallest `Q` whose expected singletons exceed 40. Verify with `code/main.py`.
2. A passport reader works at the desk but fails when the passport is 1.5 m away in a bag. Explain in terms of coupling mechanism and frequency why this is expected behavior for 13.56 MHz HF RFID, and what would change at 915 MHz UHF.
3. A volcano-monitoring sensor mesh loses all data from the far rim after three weeks. Battery telemetry shows the two nodes nearest the sink at 4%. Name the failure mode, the evidence that confirms it, and one topology change that would have delayed it.
4. Classify each as de facto or de jure and name the owning body: `Bluetooth`, `HTTP`, `802.3`, `X.509`, `RFC 791`. For the de facto ones, state which de jure body later adopted or standardized them.
5. ISM band allocation differs: US UHF RFID uses 902–928 MHz, Europe uses 865–868 MHz. Which ITU sector owns this, and what concrete interoperability failure does a single-region tag cause for a global supply chain?
6. RFID tags now carry rewritable memory. Explain, citing the malware concern from the source, why "a tag is just an ID number" is an unsafe assumption, and one security limit that prevents strong crypto on a passive tag.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Backscatter | "The tag transmits back" | The tag never generates a carrier; it modulates how it *reflects* the reader's continuous wave by switching antenna impedance |
| Passive RFID | "Battery-free tag" | The reader's RF field supplies *all* operating energy; range is path-loss limited to a few meters at UHF |
| Singulation | "Reading the tag" | Isolating one tag from many via slotted-ALOHA so its `EPC` can be read without collision |
| `Q` parameter | "A reader setting" | The slot-count exponent: `2^Q` slots per round; too small ⇒ collisions, too large ⇒ wasted idle slots |
| EPC | "The barcode number" | 96-bit Electronic Product Code carried in the tag, returned with a CRC after the reader `ACK`s the `RN16` |
| Multihop mesh | "Sensor WiFi" | Energy-constrained nodes relay each other's packets toward a sink (802.15.4); range and battery come from cooperation, not bigger radios |
| De jure standard | "An official standard" | Ratified by a formal body (ISO `IS`, IEEE 802, ITU-T Recommendation, IETF `RFC`) with a defined change process |
| De facto standard | "What everyone uses" | Adopted by usage with no formal plan (HTTP, Bluetooth); may later be ratified de jure |
| ISO | "Acronym for the standards org" | Deliberately *not* an acronym — a language-neutral name for the International Organization for Standardization |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, Ch. 1 — "RFID and Sensor Networks" and "Network Standardization (Who's Who)."
- EPCglobal / GS1 **EPC UHF Gen2 Air Interface Protocol**, harmonized as **ISO/IEC 18000-63** (UHF RFID, 860–960 MHz).
- **ISO/IEC 14443** and **ISO/IEC 15693** — HF (13.56 MHz) proximity and vicinity cards (passports, transit).
- **IEEE 802.15.4** — low-rate wireless PAN PHY/MAC underlying ZigBee and 6LoWPAN sensor meshes.
- **RFC 4944** — Transmission of IPv6 Packets over IEEE 802.15.4 Networks (6LoWPAN).
- ITU-T Recommendation **X.509** (PKI certificates) and **H.264** (also ISO/IEC MPEG-4 AVC) — examples of cross-body ratification.
- **RFC 2026** — "The Internet Standards Process," the IETF's own description of Internet-Draft → RFC.
