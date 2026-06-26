# Metric Units, the Hybrid Reference Model, and the Book Outline

> Networking lives or dies on unit arithmetic. A "1-Mbps" line moves **10⁶ bits/sec**, but a "1-KB" memory holds **1024 bytes** — and confusing the two is how engineers ship disks that look 7% smaller than the box promised. This lesson pins down the metric prefixes (milli 10⁻³ through yotta 10²⁴), the lowercase-`b`/uppercase-`B` bit-versus-byte trap, and the `kbps`/`Mbps`/`Gbps`/`Tbps` line-rate convention (powers of ten) against the `KB`/`MB`/`GB`/`TB` storage convention (powers of two). It then maps the whole book onto the **hybrid reference model**: a five-layer stack — Physical, Link, Network, Transport, Application — that borrows OSI's clean layering (dropping the unused Presentation and Session layers) and TCP/IP's proven protocols (IP, TCP, UDP, HTTP, DNS, RTP). Each chapter of the course climbs one rung: Chap. 2 covers transmission and the physical layer (DSL, the PSTN, cable TV); Chaps. 3–4 split the data link layer into point-to-point framing/error control and the medium-access sublayer (802.11, classic Ethernet, switched Ethernet, RFID); Chap. 5 is the network layer (routing, congestion, QoS, internetworking); Chap. 6 is the transport layer (UDP, TCP, reliability); Chap. 7 is the application layer (DNS, email, the Web, streaming, CDNs); Chap. 8 is security (cryptography and its collisions with privacy). The failure mode this lesson targets is the engineer who sizes a 10-Mb/s Ethernet to carry "10 MB/s" of disk traffic and wonders why buffers overflow.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Phase 1 lessons on network taxonomy, reference models (OSI and TCP/IP), and the relationship between layers, services, and protocols
**Time:** ~70 minutes

## Learning Objectives

- Convert between decimal line-rate units (kbps, Mbps, Gbps, Tbps — powers of ten) and binary storage units (KB, MB, GB, TB — powers of two) without mixing the two systems, and compute transfer time for a given file size over a given link.
- Given a real specification (e.g. a 100-psec clock, a 1-Mbps link, a 1-GB database), state the exact number of bits, bytes, or ticks the value represents and which prefix convention applies.
- Name all five layers of the hybrid reference model in order, give one concrete example protocol or technology at each layer, and explain why the OSI Presentation and Session layers were dropped.
- Map each chapter of the book onto the layer it covers and predict which layer a given problem (error detection, MAC contention, route loops, reliable byte delivery, name resolution) belongs to.
- Detect the unit-confusion bug in a capacity plan or vendor datasheet (e.g. "1 MB = 1000 KB") and compute the magnitude of the resulting error.

## The Problem

A site engineer orders a "10 Mbps" WAN circuit to back up a branch office's file server, which holds a 4-GB nightly snapshot. The nightly backup window is 60 minutes. The engineer reasons: "10 Mbps means 10 MB/s, so 4 GB / 10 MB/s = 400 seconds, well under an hour." The backup runs for 95 minutes and blows the window.

The arithmetic is wrong in two independent ways. First, **10 Mbps is 10 × 10⁶ bits/sec**, not 10 MB/s; after dividing by 8 it is only **1.25 × 10⁶ bytes/sec**. Second, **4 GB is 4 × 2³⁰ bytes**, not 4 × 10⁹ bytes, so the payload is actually 4,294,967,296 bytes. The true minimum transfer time is 4,294,967,296 / 1,250,000 ≈ 3436 seconds ≈ 57 minutes — and that is the theoretical floor, with no framing, ACK, or retransmission overhead. Add TCP/IP headers, windowing, and a little loss and 95 minutes is exactly what you would expect. The bug was never the circuit; it was conflating decimal bandwidth with binary storage and lowercase bits with uppercase bytes. This lesson is the toolkit that prevents that class of mistake, and the framework — the hybrid five-layer model — that tells you *which layer* owns each subsequent fix (framing at Layer 2, congestion window at Layer 4, and so on).

## The Concept

### Metric prefixes: the full table

Computer networking uses SI (metric) prefixes for everything that is a *rate* or a *time*, and binary interpretations of the same prefix names for *storage capacity*. The prefixes themselves, from the textbook's Fig. 1-39, are:

| Exponent | Decimal | Prefix (sub) | Exponent | Decimal | Prefix (sup) |
|---|---|---|---|---|---|
| 10⁻³ | 0.001 | milli (m) | 10³ | 1,000 | Kilo (K) |
| 10⁻⁶ | 0.000001 | micro (µ) | 10⁶ | 1,000,000 | Mega (M) |
| 10⁻⁹ | 10⁻⁹ | nano (n) | 10⁹ | 1,000,000,000 | Giga (G) |
| 10⁻¹² | 10⁻¹² | pico (p) | 10¹² | 10¹² | Tera (T) |
| 10⁻¹⁵ | 10⁻¹⁵ | femto (f) | 10¹⁵ | 10¹⁵ | Peta (P) |
| 10⁻¹⁸ | 10⁻¹⁸ | atto (a) | 10¹⁸ | 10¹⁸ | Exa (E) |
| 10⁻²¹ | 10⁻²¹ | zepto (z) | 10²¹ | 10²¹ | Zetta (Z) |
| 10⁻²⁴ | 10⁻²⁴ | yocto (y) | 10²⁴ | 10²⁴ | Yotta (Y) |

Two abbreviation rules matter in practice. Prefixes larger than 1 are **capitalized** (KB, MB, Gbps) and prefixes smaller than 1 are lowercase (ms, µs, ns, ps). The one historical exception is **kbps** for kilobits/sec, which keeps a lowercase `k`. Because both *milli* and *micro* start with `m`, the convention is `m` = milli and `µ` (Greek mu) = micro. Thus a **100-ps** (picosecond) clock ticks every 10⁻¹⁰ seconds — ten times per nanosecond — which is why the textbook uses it as a worked example.

### Bits versus bytes: the case trap

The single most expensive character in a network spec is the case of the letter `b`:

| Symbol | Means | Example |
|---|---|---|
| `b` (lowercase) | bit | 1 kbps = 1000 bits/sec |
| `B` (uppercase) | byte (8 bits) | 1 KB = 1024 bytes |

A "100-Mb/s" uplink and a "100-MB/s" file copy are **not** the same thing — the latter is eight times the former. Vendor datasheets occasionally exploit this: a storage box advertised at "500 MB/s" sustained throughput over a "4 Gb/s" Fibre Channel link is telling the truth (4 × 10⁹ / 8 = 5 × 10⁸ bytes/s, with headroom for framing), but only because the writer was careful about the case. `code/main.py` includes a `bits_to_bytes` / `bytes_to_bits` pair and a transfer-time calculator that flags any spec where the case is ambiguous or inconsistent.

### Two incompatible "kilo" systems

The deeper trap is that *the same prefix* means two different things depending on what is being measured:

| Quantity | "kilo" means | "Mega" means | Reason |
|---|---|---|---|
| Line rate (kbps, Mbps, Gbps, Tbps) | 10³ | 10⁶ | Rates are decimal; not powers of two |
| Memory / disk / file / DB size (KB, MB, GB, TB) | 2¹⁰ (1024) | 2²⁰ (1,048,576) | Memories are addressed in powers of two |

So a **1-Mbps** communication line transmits 1,000,000 bits/sec, while a **1-MB** file contains 1,048,576 bytes. A **1-GB** database is 2³⁰ = 1,073,741,824 bytes, about 7.4% more than 10⁹. Disk manufacturers use the decimal meaning (so a "1 TB" disk is 10¹² bytes ≈ 0.909 × 2⁴⁰ TiB), which is why operating systems that report in binary units show the disk as ~931 GB. The textbook's convention — and the one this course follows — is **KB, MB, GB, TB = 2¹⁰, 2²⁰, 2³⁰, 2⁴⁰ bytes** and **kbps, Mbps, Gbps, Tbps = 10³, 10⁶, 10⁹, 10¹² bits/sec**. The IEC binary prefixes (KiB, MiB, GiB, TiB, defined in ISO/IEC 80000) exist precisely to remove this ambiguity, but networking literature overwhelmingly uses the textbook's KB/MB convention, so we keep it.

### Worked example: sizing the backup window

Re-do the opening problem with the conventions fixed. A **4-GB** snapshot over a **10-Mbps** WAN:

1. Payload = 4 × 2³⁰ bytes = 4,294,967,296 bytes = 34,359,738,368 bits.
2. Line rate = 10 × 10⁶ bits/sec.
3. Floor time = 34,359,738,368 / 10,000,000 = 3435.97 s ≈ **57.27 min**.

That is the irreducible minimum if the link ran at full rate with zero overhead. Real TCP adds headers (~40 bytes/packet for IPv4 + TCP), ACK delay, and a congestion window that ramps via slow-start, so an observed 95 minutes is consistent. The point: the original "400 seconds" estimate was off by a factor of ~8.6 because it applied a binary-to-decimal swap *and* a byte-to-bit swap. `code/main.py`'s `transfer_time` function performs this computation and prints each intermediate value so you can audit it.

### The hybrid reference model: five layers

The textbook resolves the OSI-versus-TCP/IP argument by taking the **model** from OSI and the **protocols** from TCP/IP. OSI's seven layers were elegant but its top two — Presentation (syntax conversion, e.g. ASN.1, XDR) and Session (dialog control, synchronization points) — turned out to be of "little use to most applications," as the textbook puts it; real applications either fold those functions into the application layer or skip them. TCP/IP's model was informal (it barely distinguished link from physical) but its protocols won the Internet. The hybrid keeps the five layers that earned their place:

| # | Layer | Responsibility | Concrete examples |
|---|---|---|---|
| 1 | Physical | Transmit bits across a medium as signals | DSL, SONET, the PSTN, cable TV plant, 802.11 PHY |
| 2 | Link | Send finite frames between directly connected nodes with some reliability; share the channel | Ethernet, 802.11 (Wi-Fi), switched Ethernet, RFID, DSL framing |
| 3 | Network | Route packets across many hops through heterogeneous networks | IP, ICMP, routing algorithms, congestion control, QoS |
| 4 | Transport | Provide end-to-end data delivery, reliability, flow control | TCP (reliable, connection-oriented), UDP (best-effort) |
| 5 | Application | User-facing protocols and services | HTTP, SMTP, DNS, RTP, FTP, TELNET |

The model is **strictly layered**: a layer uses the service of the layer below and offers a service to the layer above, through well-defined service access points. The hybrid model keeps OSI's virtue — a clean, teachable taxonomy — and TCP/IP's virtue — protocols you can actually run. See `assets/metric-units-hybrid-model-outline.svg` for the stack with the dropped OSI layers shown faded above it.

### Why drop Presentation and Session?

OSI separated **Presentation** (data syntax / encoding negotiation — think abstract syntax versus transfer syntax, big-endian versus little-endian, compression) and **Session** (dialog control — who talks when, synchronization checkpoints for crash recovery). In practice, applications handle these inline: HTTP negotiates content via `Content-Type` and `Accept-Encoding` headers (presentation, at Layer 5); RPC frameworks embed their own session semantics; database transactions implement their own checkpoints. Few general-purpose applications wanted a separate OS-visible session service, and the OSI session protocol (X.225) saw almost no deployment. The hybrid model folds what little of these functions survives into the application layer. The lesson: a layer earns its existence only if multiple independent applications share its machinery — otherwise it is over-engineering.

### The book outline mapped onto the model

The rest of the book is a single ascent up the hybrid stack, with security as a cross-cutting capstone:

| Chapter | Layer(s) | Topics | Anchor examples |
|---|---|---|---|
| 2 | Physical | Data communications, wired + wireless transmission, the architectural (not hardware) view | PSTN, mobile phone network, cable TV, DSL |
| 3 | Link (upper) | Point-to-point framing, error detection and correction, sliding-window protocols | DSL as a real data-link protocol |
| 4 | Link (MAC sublayer) | Sharing a channel among many computers | 802.11, RFID, classic Ethernet, switched Ethernet |
| 5 | Network | Routing (static + dynamic), congestion, QoS, internetworking | IP, the Internet's network layer |
| 6 | Transport | Connection-oriented reliability, flow control, performance | UDP and TCP in detail |
| 7 | Application | Name service, email, the Web, multimedia, content delivery | DNS, SMTP, HTTP, RTP, CDNs, P2P |
| 8 | Security (all layers) | Cryptography, secure communication/email/Web, social collisions | Ciphers, TLS, PGP, censorship |

Chapters 3 and 4 split the data link layer because the medium-access problem (who gets to transmit on a shared channel — CSMA/CA, TDMA, contention windows) is logically distinct from the point-to-point problem (framing, error control, sliding window, ARQ). Chapter 8 is last because security touches every layer — you need to know what IP, TCP, and HTTP *are* before you can meaningfully secure them. `code/main.py`'s `classify_problem` function takes a problem description ("two stations collide on a shared wire," "a route advertises a loop," "a receiver reorders out-of-sequence bytes") and returns the layer it belongs to, which is the skill the outline is really training.

## Build It

1. Open `code/main.py` and read the `PREFIXES` table and the `decimal_rate_bits` / `binary_size_bytes` helpers — these encode the two conventions as explicit data.
2. Run `python3 main.py`. The demo prints the prefix table, then walks the backup-window worked example end to end, showing the bit count, the byte count, the line rate in bits/sec, and the final time in seconds and minutes.
3. Inspect `transfer_time(size_bytes, rate_bps)`. Confirm it uses `2**30` for GB and `10**6` for Mbps — the two conventions live in separate code paths so they cannot silently collide.
4. Run the `classify_problem` demo, which maps six sample problems ("CSMA/CA backoff," "TCP slow start," "BGP AS-loop," "DNS glue records") onto the five layers. Extend the keyword table with two problems of your own and confirm the classification.
5. Compare the program's "raw" output against the SVG (`assets/metric-units-hybrid-model-outline.svg`): the SVG shows the five-layer stack with the two faded OSI layers, the program shows the numeric discipline that sits *underneath* every capacity claim about that stack.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Size a backup window | `transfer_time` output with bit count and seconds | Floor time computed with binary bytes and decimal bits; overhead acknowledged as additive |
| Read a vendor datasheet | Identified unit on every line (`Mb/s` vs `MB/s`, `KB` vs `KiB`) | No silent case swap; decimal vs binary source labeled per number |
| Place a new protocol in the stack | Layer number + one-line rationale | MAC sublayer problems land in Layer 2; reliability/flow control in Layer 4 |
| Spot a unit bug in a plan | The two confusions named (byte/bit, decimal/binary) and magnitude of error quoted | Error factor stated (e.g. ~8.6×), not just "it's wrong" |
| Explain the dropped layers | Why Presentation/Session folded into Application | A concrete example (HTTP `Content-Type` as presentation, app-managed sessions) |

## Ship It

Produce the artifact `outputs/prompt-metric-units-hybrid-model-outline.md`: a short brief (one page) that (a) states the two prefix conventions as a two-row table, (b) reproduces the five-layer hybrid model with one example protocol per layer, (c) lists the eight chapters mapped to their layers, and (d) includes one worked transfer-time calculation. The brief should be readable by a teammate who has not read this lesson and should let them catch a unit-confusion bug on sight.

## Exercises

1. A 40-GB database must be copied over a 100-Mbps link in under one hour. Compute the theoretical floor time. Is it feasible? What layer-4 mechanism (TCP congestion window, header overhead) most threatens the window, and roughly how much headroom remains?
2. A clock has a 50-ps period. How many ticks occur per microsecond? Express the tick frequency in GHz and confirm the units stay consistent (no m/µ confusion).
3. A vendor sells a "2-TB" disk using the decimal convention. How many bytes is that, and how many GiB (2³⁰) does an OS reporting in binary units show? State the percentage the user "loses."
4. A colleague claims "1 GB = 1000 MB" because "mega means million." Using the textbook convention, give the correct value, name the two systems in play, and say which context each applies to.
5. Classify each of these problems to a hybrid-model layer and justify: (a) an Ethernet frame with a failed CRC, (b) two Wi-Fi stations choosing the same backoff slot, (c) a BGP update that creates an AS-level loop, (d) a TCP receiver advertising a zero window, (e) a DNS response with a stale TTL.
6. The OSI Session layer offered synchronization checkpoints for crash recovery. Name one modern system that re-implements this functionality and state which layer of the hybrid model it lives in. Why was a separate session layer not needed?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| kbps | "kilobits per second, a thousand bits" | 10³ bits/sec — decimal, lowercase k is the historical exception to the capitalization rule |
| MB | "a megabyte, a million bytes" | 2²⁰ = 1,048,576 bytes under the textbook convention — binary, not 10⁶ |
| Hybrid reference model | "the five-layer model" | OSI's layering (minus Presentation/Session) + TCP/IP's protocols; the framework the book uses |
| Presentation layer | "the OSI formatting layer" | OSI Layer 6 for syntax/encoding; dropped in the hybrid model because apps handle it inline (e.g. HTTP `Content-Type`) |
| Session layer | "the OSI dialog layer" | OSI Layer 5 for dialog control and checkpoints; dropped because few apps wanted a separate OS-visible session service |
| Physical layer | "the wires" | Hybrid Layer 1: how bits become signals on a medium (DSL, SONET, 802.11 PHY) |
| Link layer | "Ethernet and Wi-Fi" | Hybrid Layer 2: framing, error control, and medium access between directly connected nodes |
| MAC sublayer | "the part that does collision" | The lower half of Layer 2 that decides who may transmit on a shared channel (CSMA/CA, 802.11, classic Ethernet) |
| µs | "microseconds" | 10⁻⁶ seconds; uses Greek mu because both milli and micro start with `m` |

## Further Reading

- Tanenbaum, Feamster, Wetherall, *Computer Networks*, 6th ed., Chap. 1 §1.7 (Metric Units) and §1.8 (Outline of the Rest of the Book) — the source for the prefix table and the hybrid model of Fig. 1-23.
- ISO/IEC 80000-13: *Quantities and units — Part 13: Information science and technology* — defines the IEC binary prefixes KiB, MiB, GiB, TiB that disambiguate KB/MB/GB/TB.
- IEEE 1541-2002 — *Recommendation for Practice for Conformance with SI* — the standard that recommends KiB/MiB/GiB for binary multiples to avoid the disk-size confusion.
- ITU-T X.200 (1994) — *Information technology — Open Systems Interconnection — Basic Reference Model* — the seven-layer OSI model whose top two layers the hybrid model drops.
- RFC 1122 — *Requirements for Internet Hosts — Communication Layers* — codifies the TCP/IP layer model (Link, Internet, Transport, Application) whose protocols populate the hybrid model's lower four layers.
- IETF RFC 791 (IPv4) and RFC 8200 (IPv6) — the network-layer protocols placed at Layer 3 of the hybrid model.
