# RFID EPC Gen 2: tag identification, the Q-algorithm singulation, and message formats

> EPC Class-1 Generation-2 (informally "Gen 2," standardized as ISO/IEC 18000-63 by GS1 EPCglobal) is the UHF RFID air interface used in supply chains, tolls, and apparel. The band sits in 860-960 MHz (FCC 902-928 MHz, ETSI 865-868 MHz) and the protocol is strictly **reader-talks-first** — the reader transmits a **continuous wave** that the tags harvest to power themselves, and tags reply by changing whether they reflect or absorb that carrier, a low-energy technique called **backscatter**. Tag-to-reader bits travel as load-modulated pulses encoded with Miller subcarrier coding (1-8 pulse periods per symbol). Singulation uses a slotted protocol driven by the **Q-algorithm**: the reader announces a parameter `Q` (0-15) so tags pick a 16-bit random **slot counter** in `[0, 2^Q - 1]`, decrement on every Query, and reply with a 16-bit **RN16** when their counter hits 0; on a clean RN16 the reader returns an ACK and the tag transmits **PC + EPC + CRC-16**. If RN16s collide, both involved tags pick fresh slot counters and re-enter the inventory. Persistence is carried by four **inventory flags (S0, S1, S2, S3)** and a **Selected (SL) flag**, which allow multiple readers to coordinate via four independent sessions. Physical-layer timing centers on the **Tari** interval (6.25-25 us reference pulse) and a **backscatter link frequency (BLF)** from 40 kHz to 640 kHz, modulated with ASK, DSB-ASK, SSB-ASK, or PR-ASK. This lesson walks the Gen 2 inventory flow end to end, builds a singulation simulator, and decodes the Query message format.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Slotted ALOHA (Phase 5), bit-level framing and CRC, basic modulation concepts (ASK, Sec. 2.5.2)
**Time:** ~75 minutes

## Learning Objectives

- Trace the Gen 2 inventory flow (`Select -> Query -> ACK -> Req_RN -> Read/Write`) and explain why RN16 is exchanged *before* the long EPC identifier.
- Run the **Q-algorithm**: pick a `Q`, simulate tag slot-counter draws in `[0, 2^Q - 1]`, classify each slot as empty, single, or collision, and tune `Q` with `QAdjust` against observed slot statistics.
- Decode a **Query** command field by field — `Command(4) | DR(1) | M(2) | TRcal(1) | Sel(2) | Session(2) | Target(1) | Q(4) | CRC-16(5)` — and apply the **0x600**-style CRC rules (CRC-16/CCITT for memory, CRC-16/IBM for command feedback).
- Distinguish **passive** tags (powered by the reader's CW) from **active / semi-passive** tags, and explain why passive tags cannot do carrier sense or talk to each other.
- Apply the **four inventory flags (S0-S3)** and the SL flag for session-based coordination between overlapping readers, and the **state machine** (`Ready -> Arbitrate -> Reply -> Acknowledged -> Open -> Secured -> Killed`) that gates which commands a tag will obey.
- Read and write memory across the four logical banks (`Reserved`, `EPC`, `TID`, `User`), gated by **access** and **kill** passwords, and validate payloads with the Gen 2 CRC-16 (poly `0x1021`, init `0xFFFF`).

## The Problem

A distribution-center dock door reads a pallet of 1000 boxes every time it opens. Each box carries a passive UHF RFID sticker. The reader sees all 1000 tags inside its antenna field at once, but the tags cannot hear each other, cannot sense the channel, and have no batteries to synchronize their own clocks. If every tag transmits its 96-bit EPC immediately, the 1000 backscatter signals collide and the reader recovers nothing. If every tag waits a random time, the average wait stretches into seconds — too slow for a moving forklift.

Gen 2 has to solve four problems at once:

1. **Inventory unknown N tags** without carrier sense and without prior registration.
2. **Avoid wasting airtime** on collisions of the long EPC payload.
3. **Make sure each tag is read once**, even if it crosses the field multiple times or several readers overlap.
4. **Stay cheap and power-frugal**: a sticker-tag IC has to cost a few cents and run on the microwatts it can harvest from the reader's continuous wave.

The textbook answer is slotted ALOHA with an adaptive number of slots — slotted because the reader drives time, ALOHA-like because each tag picks its slot independently. Gen 2 calls it the **Q-algorithm**, after the parameter that controls slot count: `2^Q` slots, with `Q` retuned slot-by-slot based on observed occupancy.

## The Concept

Gen 2 is two coupled layers: a **physical layer** that defines a continuous-wave, half-duplex, backscatter channel, and a **tag-identification (MAC) layer** that drives the reader-talks-first inventory. The SVG shows the inventory with a reader radiating its field, eight tagged boxes, and a slot-by-slot trace; `code/main.py` simulates the Q-algorithm end to end.

### Passive vs. active tags

A **Class-1 passive tag** is an inductive sticker. The antenna and a tiny IC dot harvest energy from the reader's continuous wave (typically a fraction of a milliwatt), wake the digital logic, and reflect or absorb the carrier to send bits. It costs cents and lasts forever (no battery), but the airtime and range are limited. An **active tag** carries its own battery, runs a transmitter, and can be heard at tens of meters, but costs dollars and has a finite lifetime. A **semi-passive (or BAP)** tag has a battery for the IC but still modulates the reader's carrier — it gets the long range of active tags for the downlink reply while keeping the digital side alive between reads. Gen 2 in this lesson is the Class-1 passive case, which is the one Tanenbaum covers.

### UHF bands and regional regulation

| Region | Band | Channels | Notes |
|---|---|---|---|
| FCC (US, Americas) | 902-928 MHz | hopping across the band | must change frequency at least every 400 ms |
| ETSI (Europe) | 865-868 MHz | 10 fixed channels (low-power + 4 high-power) | tighter duty-cycle rules |
| Japan (ARIB) | 916.7-920.8 MHz | subdivided | regional profiles live in EPCglobal docs |
| China | 840-845 / 920-925 MHz | regional | per-local regulation |

The reader sends its command on one channel, then **hops** at the cadence the regulator demands to spread the energy and limit interference. A tag replies on the same channel using BLF (`backscatter link frequency`) derived from the reader's `TRcal` parameter: `BLF = DR / TRcal`, with `DR` (divide ratio) typically 1 and `BLF` settling into the 40-640 kHz range the spec allows.

### The physical layer: continuous wave, ASK, backscatter

The reader is **always transmitting** during the inventory. When the reader wants to send bits, it amplitude-modulates the carrier with two amplitudes (DSB-ASK), one amplitude (SSB-ASK), or phase-reversed ASK (PR-ASK); a `0` bit has a brief low-power period and a `1` bit has a longer one — readers call this **PIE, or pulse-interval encoding**. The reference pulse width is the **Tari**, ranging from 6.25 us to 25 us; the data-1 pulse is roughly 1.5-2 Tari long and the data-0 pulse roughly 1 Tari.

For the tag's reply, the reader switches to a clean unmodulated carrier. The tag then alternates its antenna's impedance — reflecting or absorbing the carrier — to produce a backscatter tone at the BLF. The reader's own transmitted carrier is much stronger, but the tag's modulation is at a different frequency (the BLF) and the receiver subtracts the carrier to recover the tag bits. The tag encodes bits with **Miller subcarrier modulation**: 1-8 BLF cycles per bit, with the convention that a `0` has more transitions than a `1`. More subcarrier cycles mean more reliable decoding at the cost of airtime; Gen 2 lets the reader pick the `M` (modulation depth) parameter to trade them off.

### The inventory flow: Select -> Query -> ACK -> Req_RN -> Read

The five-message dance that reads one tag:

1. **Select** — the reader broadcasts a `Sel` parameter (`00`, `01`, `10`, `11`) and a mask. Tags whose EPC matches the mask flip their **SL** (Selected) flag on. The reader uses Select to scope the next inventory to a subset (e.g. "all jeans, no shirts") without affecting tags outside the mask.
2. **Query(Q, Sel, Session, Target)** — the reader starts an inventory round and announces a slot range `2^Q`. Tags whose session+target state matches drop a fresh 16-bit slot counter uniformly from `[0, 2^Q - 1]`. If their counter is non-zero, they decrement on each subsequent **QRepeat** and stay silent. If the counter hits 0, they jump from `Arbitrate` to `Reply` and send a 16-bit **RN16** (a freshly random handle, not a slot ID).
3. **ACK(RN16)** — if the reader hears exactly one RN16, it returns an ACK echoing the same RN16. Tags whose RN16 matches transition to `Acknowledged` and prepare their EPC.
4. **Req_RN(RN16_or_handle)** — the reader requests the EPC, optionally with a fresh handle. The tag replies with **PC + EPC + CRC-16**. (The first response after Query actually puts the EPC directly; Req_RN is the formal next step in the secured path.)
5. **Read / Write / Lock / Kill** — once in the `Open` or `Secured` state, the reader can address memory in any of the four banks using the **handle** (which replaced RN16) as a soft MAC. The access password gates writes and access to reserved memory.

The critical design choice is **why RN16 first**: EPCs are long (96+ bits) and a collision on the long payload wastes airtime. RN16s are short (16 bits) and a collision on RN16 only costs the reader the slot it already allocated. The `ACK` step is a fast "did I get a clean slot?" handshake that protects the long EPC from collision.

### The Q-algorithm, walked through with Q=2 and four tags

`Q=2` means `2^2 = 4` slots. Suppose four tags A, B, C, D each draw a slot counter:

| Tag | Drawn counter | Path |
|---|---|---|
| A | 2 | silent in slot 0, silent in slot 1, replies in slot 2 |
| B | 3 | silent in slot 0, silent in slot 1, silent in slot 2, replies in slot 3 |
| C | 0 | replies in slot 0 |
| D | 0 | replies in slot 0 — collides with C |

Slot 0 has two RN16s — collision. Both C and D fail to decode the ACK, so they drop new counters and try again next round. Slot 1 is empty (no counter landed there). Slot 2 sees A's RN16 only, the reader ACKs, A returns its EPC, and A is **singulated** (it flips its session flag so it skips the next Query). Slot 3 sees B alone, same outcome. After two rounds, all four tags are inventoried.

A useful rule of thumb from slotted ALOHA: when `2^Q ≈ N`, the load is near `1` and efficiency is near `1/e ≈ 36.8%`. If the reader sees mostly empty slots, it sends **QAdjust** to shrink Q by 1 (halving slot count). If it sees mostly collisions, it grows Q by 1 (doubling slot count). This is Gen 2's analog of Ethernet's binary exponential backoff.

### The slot-counter state machine and collided-slot recovery

The tag's MAC state machine is the heart of singulation. From `Ready` (just powered up), the tag listens for Select/Query. On Query matching its session+target+SL flags, it draws a fresh counter from `[0, 2^Q - 1]` and enters `Arbitrate`. In `Arbitrate`, it decrements on every QRepeat and, when the counter reaches zero, enters `Reply` and transmits its RN16.

From `Reply` three things can happen:

- **ACK matches RN16** -> `Acknowledged` -> transmit PC+EPC+CRC-16 -> `Open` (after Req_RN) or `Secured` (if the access password was presented). Tag sets its session flag (per `Target`/`Sel`) so it skips the next Query in that session.
- **No valid ACK** -> tag assumes collision, draws a new counter, and re-enters `Arbitrate`. This is the **collided-slot recovery** path and is what makes Gen 2 self-healing.
- **No response at all** -> the reader simply moves on with QRepeat; the tag eventually times out the slot in `Arbitrate` and tries again next round.

Once `Acknowledged`, the tag uses the handle the reader gave it as a soft MAC. After access-password-gated operations it can move to `Secured`. The **Kill** command wipes memory and locks the tag permanently (used when items leave the supply chain).

### Persistence: S0, S1, S2, S3 and SL

Tags track up to four independent **sessions** at once. Each session has two flags: a **persistence** flag (the "S" flag, e.g. `S0`) and a flag saying whether the tag has already been inventoried in this session. The Query command names `Sel` (which tags respond, via the SL flag), `Session` (which of the four flag pairs to flip), and `Target` (whether to flip `A->B` or `B->A`). Two readers with overlapping coverage can run inventories in different sessions without clobbering each other's flag state. After being read in session `S2`, a tag keeps the `S2 flag = B`; the next Query with `Target=A` in `S2` will pick it up again, while a Query in `S0` ignores the `S2` state entirely.

The **SL (Selected) flag** is separate from the four sessions. Select sets it; it lets the reader scope a Query to a subset ("jeans only") without permanently changing session state.

### Memory: four banks, two passwords

Gen 2 tags expose four logical memory banks, each at a 32-bit word address:

| Bank | Address prefix | Contents |
|---|---|---|
| `00` Reserved | 0x00..0x3F | kill pwd (0x00..0x01), access pwd (0x02..0x03), EPC length controls |
| `01` EPC | 0x00.. | CRC-16 (2 B), PC (2 B), then the EPC (typically 96 bits = 12 B) |
| `10` TID | 0x00.. | tag serial number, vendor, model — usually read-only |
| `11` User | 0x00.. | free-form; optional, vendor-defined |

The **PC** (Protocol Control) word encodes EPC length, the XPC indicator, and a User-memory indicator. The access password gates the `Secured` state (and most writes); the kill password gates the `Kill` command. Both default to zero in most deployments — a real security posture requires non-zero passwords. The simulator keeps these as a `Bank` view per tag.

### CRCs: two polynomials

Gen 2 uses **two different CRC-16s** and the distinction matters:

- **CRC-16 for command feedback and EPC storage**: polynomial `0x1021`, initial value `0xFFFF`, MSB-first. This is CRC-16/CCITT-FALSE.
- **CRC-16 for Query / ACK / Req_RN** command feedback: polynomial `0x8408`, initial value `0xFFFF`, reflected input/output (CRC-16/IBM or "CRC-16/AUTOSAR"). The Query trailer is a 5-bit **short CRC** computed over the preceding bits with this polynomial.

The simulator computes both and reports which one each payload uses.

### Physical-layer timing in one paragraph

`Tari` is the reference pulse interval: 6.25 us, 12.5 us, or 25 us (the latter for the most robust mode). `BLF` is `1 / Tari` for the basic mode, or derived from `TRcal`: `BLF = DR / TRcal` with `DR ∈ {1, 8/3}` and `TRcal` between 1.5 and 3 Tari; the spec lists allowed combinations landing BLF at 40, 80, 160, 213, 256, 320, 640 kHz. Modulation depth `M` is encoded in two bits: `00 = DSB-ASK`, `01 = SSB-ASK`, `10 = PR-ASK`, `11 = DSB-ASK`. Miller subcarrier cycles per bit (1 to 8) and the BLF together fix the tag-to-reader bitrate.

## Build It

`code/main.py` is a stdlib-only simulator of Gen 2 singulation. Two halves:

1. **Singulation simulator** — a `Tag` class with EPC, slot counter, session flags (S0-S3), SL flag, and state; a `Reader` that runs `Query(Q)`, collects RN16s from the air (modelled as a dict `slot -> [tags]`), decides single/collision/empty per slot, sends `ACK` to singletons, fetches PC+EPC+CRC-16, and tunes `Q` via `QAdjust` based on a simple rule. The simulator prints a slot-by-slot trace for Q=2 and 8 tags, including the EPC for every singulated tag.
2. **Message-format helpers** — functions to build and parse a `Query` command field by field, plus a CRC-16 implementation for both polynomials (`0x1021` and `0x8408`). The `__main__` block prints the slot map for Q=2 with 8 tags, the slot-occupancy histogram, and the final EPC list.

Run `python3 code/main.py`. Try changing `Q` to 1 or 3 and watch the collision rate shift. Try `QAdjust` thresholds to see how adaptive Q behaves under burst load.

## Use It

| Task | Evidence | What good looks like |
|---|---|---|
| Decode a Query frame | `Command=1000`, fields `DR,M,TRcal,Sel,Session,Target,Q` | You name each bit, compute slot range `2^Q`, and verify the 5-bit CRC-16 |
| Classify a slot | 0, 1, or >=2 RN16s | `empty` / `singulated` / `collision`; collision tags draw fresh counters next round |
| Pick Q | `2^Q ≈ N tags` | Q=4 for ~16 tags; Q=8 for ~256; tune with QAdjust on empty/collision streak |
| Singulate a tag | `ACK(RN16)` -> `PC+EPC+CRC-16` | RN16 is short (16 b), EPC long (96+ b); ACK gate keeps EPC off the wire if RN16 collided |
| Coordinate two readers | Different `Session` | Each reader toggles S0..S3 independently; tag tracks all four |
| Protect memory | `Read / Write / Lock` with handle + password | Access pwd gates `Secured`; kill pwd gates `Kill` |
| Check a CRC | Recompute over the payload | Match for command feedback and EPC trailer; mismatch = drop |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **Gen 2 inventory flow cheat sheet**: the five-message dance, Q-algorithm state diagram, and slot-occupancy decision tree.
- A **Query frame table** with every field's bit count and meaning, plus both CRC-16 polynomials.
- A **session-flag table** showing how `S0..S3` and the `SL` flag let multiple readers coordinate on overlapping populations.
- The **singulation simulator** (`code/main.py`) wired to your own tag populations.

Start from `outputs/prompt-rfid-epc-gen2-singulation.md`.

## Exercises

1. A dock door has `N = 200` tags in the field. What `Q` gives the best expected efficiency? Use `2^Q ≈ N` and the slotted-ALOHA peak `1/e`. Now run `code/main.py` with `Q=4`, `Q=7`, `Q=8` and report collisions, empty slots, and total rounds for `N=200`.
2. The reader sees five `collided` slots and one `empty` slot in a row at `Q=4`. Apply `QAdjust` (it sends the new Q once and tags refresh counters). What Q do you propose next, and why? Re-run with `Q=5` and confirm the collision rate drops.
3. A tag with EPC `E280-1160-6000-0200-DB7C-1234-AB` is in state `Open`. Walk the message sequence the reader uses to (a) write `0xDEADBEEF` to user-memory word `0x10`, and (b) re-lock the tag so the access password is required for the next Write. Include the password handshake.
4. Two readers with overlapping coverage run continuous inventory. Explain which combination of `Session` and `Target` keeps them from reading the same tag twice in the same round and lets each re-flag tags in its own session independently.
5. The CRC-16 in a stored EPC fails verification. The reader is in `Secured` state with the access password. List the three reader-side actions (in order) Gen 2 recommends before re-trying the read, and the one tag-side action if the mismatch persists.
6. Decode the Query frame `1000 10 01 1 00 10 0 0101 11010`. Name every field, compute the slot range, and identify the SL state, the target flag flip direction, and the CRC-16 polynomial used.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Gen 2 | "the EPC standard" | EPC Class-1 Generation-2 RFID, ISO/IEC 18000-63, GS1 EPCglobal, UHF 860-960 MHz |
| Passive tag | "no battery" | Powered by the reader's continuous wave; replies via backscatter modulation |
| Continuous wave | "the reader signal" | Unmodulated RF the reader transmits for power and as the carrier the tag modulates |
| Backscatter | "tag reflect/absorb" | Tag toggles antenna impedance to encode bits on the reader's carrier (low-energy, half-duplex) |
| Tari | "pulse width" | Reference pulse interval for PIE encoding, 6.25-25 us |
| BLF | "tag bit clock" | Backscatter link frequency, 40-640 kHz, derived from Tari and TRcal |
| Q-algorithm | "slotted singulation" | Reader picks Q, tags draw `2^Q`-wide slot counter, reply on counter==0; QAdjust retunes Q |
| RN16 | "short handle" | 16-bit random handle sent first so collisions don't waste the long EPC |
| ACK / Req_RN | "the handshake" | ACK echoes RN16; Req_RN trades handle for PC+EPC+CRC-16 |
| Inventory flags | "S0, S1, S2, S3" | Per-session flag pairs that let multiple readers coordinate on overlapping populations |
| SL flag | "Selected" | Per-tag flag flipped by Select to scope a Query to a subset |
| CRC-16 / CCITT-FALSE | "the EPC CRC" | Poly `0x1021`, init `0xFFFF`, MSB-first — used for memory/EPC |
| CRC-16 / IBM | "the command CRC" | Poly `0x8408`, init `0xFFFF`, reflected — used for command feedback (5-bit short form in Query) |
| Miller subcarrier | "tag modulation" | 1-8 BLF cycles per bit; more cycles = more robust but slower |
| Access / Kill passwords | "the gates" | Two 32-bit passwords; access -> Secured, kill -> permanent deactivation |

## Further Reading

- **EPC Radio-Frequency Identity Protocols Generation-2 UHF RFID** (EPCglobal, ratified as ISO/IEC 18000-63) — the air-interface spec, query/ACK/Req_RN message formats, state machine, and CRC-16s.
- **GS1 EPC Tag Data Standard (TDS)** — the EPC structure, the PC word, and how a 96-bit EPC encodes a company prefix + item reference + serial.
- **ISO/IEC 18000-63** — the ISO mirror of the EPCglobal Gen 2 standard.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §4.7 "RFID" — the source chapter for this lesson.
- **EPCglobal "Regulatory Status for RFID using UHF"** — the per-region frequency/duty-cycle tables (FCC, ETSI, ARIB, MIC, etc.).
- Want, R. (2006), "RFID Explained," *Synthesis Lectures on Mobile and Pervasive Computing* — short, vendor-friendly overview of the Gen 2 design.
- Sample, A. et al. (2008), "Design of an RFID-Based Battery-Free Programmable Sensing Platform," *IEEE Trans. Instrumentation and Measurement* — the "research tag with sensors" footnote.