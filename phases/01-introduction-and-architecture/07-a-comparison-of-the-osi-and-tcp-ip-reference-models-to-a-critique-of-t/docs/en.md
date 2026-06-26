# A Comparison of the OSI and TCP/IP Reference Models, and a Critique of Both

> OSI and TCP/IP share a layered, end-to-end philosophy but diverge in ways that still shape protocol design. OSI has **7 layers**, TCP/IP has **4**; OSI cleanly separates **services, interfaces, and protocols** (a layer's *what*, *how to call it*, *how it works internally*), while TCP/IP blurs them — its internet layer offers only `SEND IP PACKET` / `RECEIVE IP PACKET`. OSI is model-before-protocols (general but mismatched to reality, needing convergence sublayers); TCP/IP is protocols-first (so the model only describes TCP/IP and is "completely impossible" to apply to Bluetooth). OSI mandates connection-oriented transport; TCP/IP gives a choice — connectionless **UDP** (RFC 768, 8-byte header) versus connection-oriented **TCP** (RFC 793, 20-byte minimum header, three-way handshake). OSI was crushed by Clark's "apocalypse of the two elephants" bad-timing problem plus near-empty session/presentation layers. TCP/IP's host-to-network "layer" is really an interface and conflates physical with data-link. This lesson turns those critiques into a runnable scoring tool.

**Type:** Learn
**Languages:** Diagrams, standards
**Prerequisites:** Lessons 01–06 of Phase 1 (layering, protocol stacks, the OSI and TCP/IP models, connection-oriented vs connectionless service)
**Time:** ~70 minutes

## Learning Objectives

- Map the 7 OSI layers onto the 4 TCP/IP layers and state exactly which OSI layers have no TCP/IP equivalent and why.
- Distinguish **service**, **interface**, and **protocol** precisely, and explain why TCP/IP failing this distinction makes it a poor design guide.
- Explain "model-first" (OSI) versus "protocol-first" (TCP/IP) ordering and name one concrete failure each produced (convergence sublayers; Bluetooth being undescribable).
- Recite the four OSI failure reasons (bad timing, bad technology, bad implementations, bad politics) and tie "bad timing" to David Clark's apocalypse-of-the-two-elephants.
- List the five specific TCP/IP critiques (no service/interface/protocol split, not general, host-to-network is an interface not a layer, no physical/data-link split, ad-hoc protocols like TELNET).
- Use `code/main.py` to score a real-world model-vs-protocol decision and justify the result.

## The Problem

You join a team standardizing a new industrial sensor network. One architect insists the design document follow "the OSI seven layers," draws a session layer and a presentation layer, and asks who owns them. Another architect says "we run on IP, just use the TCP/IP four-layer model" — and then cannot decide where the 802.15.4 radio framing belongs, because TCP/IP lumps "everything below IP" into one host-to-network box.

Both are repeating decades-old mistakes. The OSI advocate is reserving slots (session, presentation) that real protocols leave nearly empty, and is about to discover the model does not match the hardware, forcing ad-hoc "convergence sublayers." The TCP/IP advocate is using a model that "is not at all general and is poorly suited to describing any protocol stack other than TCP/IP." To referee this, you need to know what each model actually got right and wrong — not as trivia, but as a checklist you can apply to any architecture review. See the model overlay in [`assets/a-comparison-of-the-osi-and-tcp-ip-reference-models-to-a-critique-of-t.svg`](../assets/a-comparison-of-the-osi-and-tcp-ip-reference-models-to-a-critique-of-t.svg).

## The Concept

### Layer-by-layer overlay

Both models stack independent protocols and both provide an end-to-end, network-independent transport service: layers up through transport are the **transport provider**; layers above transport are application-oriented **users** of that service. The split happens below and above transport.

| OSI layer | # | TCP/IP layer | Notes |
|---|---|---|---|
| Application | 7 | Application | TCP/IP folds OSI 5–7 into one. HTTP, SMTP, DNS, TELNET all live here. |
| Presentation | 6 | — | Nearly empty in OSI; encoding/encryption pushed into apps (e.g. TLS, JSON). |
| Session | 5 | — | Nearly empty in OSI; dialog/sync rarely used as a distinct layer. |
| Transport | 4 | Transport (L4) | Both have it. OSI: connection-oriented only. TCP/IP: TCP **or** UDP. |
| Network | 3 | Internet (L3) | OSI offers connectionless **and** connection-oriented; TCP/IP only connectionless (IP). |
| Data Link | 2 | Host-to-Network | TCP/IP collapses L1+L2 into one under-specified box. |
| Physical | 1 | Host-to-Network | OSI separates them; TCP/IP does not. |

The clean correspondences are network, transport, and application. Everything else is where the critiques live.

### Service vs interface vs protocol — the distinction OSI nailed

The single biggest contribution of OSI is making three concepts explicit, and keeping them separate:

- **Service** — *what* a layer does for the layer above. Its semantics. The service definition says nothing about implementation.
- **Interface** — *how* the layer above invokes it: the parameters passed and results expected. Still says nothing about internals.
- **Protocol** — the layer's *own business*: the peer rules it uses internally. A layer may swap protocols freely without affecting higher layers, as long as the service stays the same.

This is exactly the object-oriented idea: an object's methods' semantics are its **service**, the methods' parameters/results are its **interface**, and the internal code is its **protocol** — invisible outside the object. Because OSI hides protocols behind services, OSI protocols "can be replaced relatively easily as the technology changes." TCP/IP "did not originally clearly distinguish" these; the internet layer's only real services are `SEND IP PACKET` and `RECEIVE IP PACKET`, so the model "is not much of a guide for designing new networks using new technologies." `code/main.py` encodes this as a scored criterion.

### Model-first vs protocol-first ordering

| Property | OSI | TCP/IP |
|---|---|---|
| Order | Model devised **before** protocols | Protocols came **first**, model described them |
| Generality | General, unbiased toward any stack | Describes only TCP/IP; cannot describe Bluetooth |
| Fit to reality | Poor — needed convergence sublayers; data-link sublayer hacked in for broadcast nets | Perfect — model fit the protocols exactly |
| Designer experience | Little; wrong functionality placed in wrong layers | Lots; protocols were already deployed |

OSI's order kept it neutral but the designers "did not have a good idea of which functionality to put in which layer." The data link layer originally handled only point-to-point links; when broadcast networks (LANs) appeared, a sublayer had to be **hacked into** the model — the MAC sublayer. Real OSI networks "did not match the required service specifications," so convergence sublayers were grafted on to paper over differences. TCP/IP had the reverse trade: a perfect fit to its own protocols, useless for anything else.

### Connection-oriented vs connectionless: where each model places choice

The OSI model supports both connectionless and connection-oriented service in the **network** layer, but **only connection-oriented** in the transport layer — "where it counts," because transport is the service the user actually sees. TCP/IP inverts this: the network layer is **connectionless only** (IP is best-effort, RFC 791), but the transport layer offers **both**, giving users a choice. That choice matters for simple request–response traffic:

| | Header | Connection | Reliability | Use |
|---|---|---|---|---|
| **UDP** (RFC 768) | 8 bytes (src port, dst port, length, checksum) | None | None — best effort | DNS query/response, one-shot RPC |
| **TCP** (RFC 793) | 20 bytes min (ports, 32-bit seq/ack, flags, window, checksum) | 3-way handshake (SYN, SYN-ACK, ACK) | Sequencing, retransmission, flow control | HTTP, SMTP, bulk transfer |

A DNS lookup over UDP is one request and one reply — two datagrams — versus TCP's minimum of a SYN/SYN-ACK/ACK before any data and a FIN exchange after. OSI's "transport must be connection-oriented" rule would have forbidden the cheap UDP path.

### Why OSI failed — the four reasons

1. **Bad timing.** David Clark's *apocalypse of the two elephants*: a standard must be written in the trough between the first elephant (a burst of research activity) and the second (the billion-dollar wave of corporate investment). Written too early it codifies a poorly-understood subject; too late and everyone has already invested in incompatible approaches. OSI got **crushed** — TCP/IP was already in widespread use at research universities, vendors were cautiously shipping it, and nobody wanted to support a second stack first. With every company waiting for every other, OSI never happened.
2. **Bad technology.** Seven layers was "more political than technical." Two layers (session, presentation) are nearly empty; two (data link, network) are overfull. The printed standards occupy "a significant fraction of a meter of paper" — complex, hard to implement, inefficient. Saltzer's end-to-end argument also shows error control must live in the highest layer, so repeating addressing/flow-control/error-control in every layer is wasteful.
3. **Bad implementations.** Early OSI stacks were "huge, unwieldy, and slow"; people associated "OSI" with "poor quality" and the image stuck. By contrast, an early TCP/IP implementation shipped free in Berkeley UNIX and was good — driving an upward spiral of users → improvements → more users.
4. **Bad politics.** TCP/IP was seen as part of UNIX (academic apple-pie); OSI was seen as a creature of government bureaucrats and telecom ministries forcing a technically inferior standard on the people in the trenches.

### Why TCP/IP is also flawed — the five critiques

1. **No service/interface/protocol distinction.** Good software engineering separates specification from implementation; OSI does this carefully, TCP/IP does not — so the model poorly guides new designs.
2. **Not general.** The model only describes TCP/IP; using it for Bluetooth "is completely impossible."
3. **Host-to-network is an interface, not a layer.** It sits *between* the network and data-link layers. Conflating an interface with a layer is sloppy and crucial to get right.
4. **No physical/data-link split.** The physical layer concerns copper/fiber/wireless transmission characteristics; the data-link layer delimits frame start/end and delivers frames with a chosen reliability. These are completely different jobs; a proper model keeps them separate. TCP/IP does not.
5. **Ad-hoc upper protocols.** IP and TCP were carefully designed, but many others were "produced by a couple of graduate students hacking away until they got tired," then distributed free and became entrenched. TELNET, designed for a 10-character-per-second mechanical Teletype, knows nothing of GUIs or mice yet survives 30+ years later.

## Build It

`code/main.py` turns these critiques into a deterministic scorecard. To use it:

1. Encode each model as a set of boolean **criteria** (clean service/interface/protocol split, separates physical from data link, general beyond its own stack, lets transport be connectionless, layer count parsimony, protocols-before-model maturity).
2. Run `python3 main.py` to print the layer overlay, the per-criterion scores for OSI and TCP/IP, and a verdict for a sample architecture-review scenario.
3. Feed in your own scenario (e.g. "describe an 802.15.4 sensor stack") and read which model the tool recommends and why.
4. Inspect the connection-oriented/connectionless placement table the script generates to confirm where UDP and TCP fit.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Overlay the models | The 7-to-4 mapping table | You can name session + presentation as the OSI layers with no TCP/IP peer, and physical+data-link as the pair TCP/IP merges |
| Defend the OSI strength | Service vs interface vs protocol definitions | You explain that hiding the protocol behind a stable service is what lets a layer be re-implemented without breaking higher layers |
| Defend the TCP/IP strength | Protocol-first ordering, perfect fit | You explain why TCP/IP "just works" for IP stacks but cannot describe Bluetooth |
| Justify a transport choice | UDP 8-byte vs TCP 20-byte header, handshake cost | You pick UDP for a single DNS query and explain OSI would have forbidden it |
| Audit an architecture | `code/main.py` scorecard output | The recommended model matches the critique that dominates the scenario |

## Ship It

Produce one artifact under `outputs/`:

- A **model-selection scorecard** generated by `code/main.py` for a real architecture you are reviewing, with the winning model and the deciding criterion annotated.
- Or a one-page **critique runbook**: the four OSI failure reasons and five TCP/IP critiques as a review checklist, each paired with a modern example (TLS-in-app for the empty presentation layer; MAC sublayer for the hacked-in broadcast support; 802.15.4 for "host-to-network is too coarse").

## Exercises

1. A standards committee proposes a new protocol stack and publishes the reference model **before** any implementation exists. Using the apocalypse-of-the-two-elephants, argue the timing risk and name the OSI-style failure mode they are most likely to repeat (hint: convergence sublayers).
2. Your TCP/IP-only model cannot cleanly place an 802.15.4 radio plus 6LoWPAN adaptation layer. Which two specific TCP/IP critiques does this expose? Show where OSI would have put each piece.
3. A junior engineer says "session and presentation layers are pointless — TCP/IP proved it." Give the OSI rebuttal: name a modern protocol/feature that does session-like or presentation-like work, and explain why it lives in the application layer instead.
4. Take a single DNS A-record lookup. Count the datagrams over UDP versus the segments TCP would require (handshake + query + response + teardown). Explain why OSI's "transport is connection-oriented only" rule is the wrong default here.
5. Run `code/main.py` for the scenario "design a brand-new IoT protocol family that must outlive today's radios." Which model does it recommend, and which single criterion decides it? Would you override the tool? Justify.
6. The host-to-network "layer" is called an interface, not a layer. Write the one-sentence test that distinguishes a layer from an interface, and apply it to TCP/IP's host-to-network box.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Service | "What a layer is" | The semantics a layer offers the layer above — *what*, never *how*; OSI defines it independently of any protocol |
| Interface | "The API" | The exact parameters and results the layer above passes to invoke the service; says nothing about internals |
| Protocol | "The standard" | A layer's internal peer rules — its own business; can be swapped without touching higher layers if the service is unchanged |
| Convergence sublayer | "Extra OSI complexity" | A patch grafted onto OSI because real networks did not match the model's required service specs |
| Apocalypse of the two elephants | "OSI was just late" | Clark's model: standards must land in the trough between the research-activity elephant and the investment elephant, or get crushed |
| Host-to-network | "TCP/IP layer 1" | Not a true layer — an interface between network and data-link concerns that also wrongly merges physical and data-link |
| Connectionless transport | "UDP" | Best-effort datagram service OSI forbade at transport; TCP/IP allows it, which is why cheap request–response works |

## Further Reading

- **RFC 791** — Internet Protocol (IP): the connectionless internet layer.
- **RFC 768** — User Datagram Protocol (UDP): the 8-byte connectionless transport TCP/IP permits and OSI forbade.
- **RFC 793** (updated by **RFC 9293**) — Transmission Control Protocol (TCP): connection-oriented transport, three-way handshake.
- **RFC 854** — TELNET protocol specification: the ad-hoc, Teletype-era protocol still in use.
- **ISO/IEC 7498-1** — the OSI Basic Reference Model: the seven layers, services, and the service/interface/protocol distinction.
- Saltzer, Reed, Clark (1984), "End-to-End Arguments in System Design" — why error control belongs in the highest layer.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §1.4.4–1.4.6 — the comparison and both critiques.
- Piscitello & Chapin (1993), *Open Systems Networking: TCP/IP and OSI* — a full book comparing the two.
