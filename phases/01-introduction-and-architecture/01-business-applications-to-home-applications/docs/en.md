# Business Applications to Home Applications

> Networks earn their keep by sharing resources and people, not wires. Two interaction models dominate: the **client-server model**, where one server process answers request/reply messages from hundreds or thousands of client processes (the basis of HTTP, where a client opens a TCP connection to port 80/443, sends a `GET` request line, and blocks on a reply), and **peer-to-peer (P2P)**, where every node is symmetric — both requester and responder — with no fixed division of roles (BitTorrent, online auctions, and email at the transport level). The same request/reply pattern scales from a New York salesperson reaching a Singapore inventory database over a **VPN** to a home user loading a Web page. Quantifying the "why connect at all" question, **Metcalfe's law** says a network's value grows as roughly n(n-1)/2 — the number of distinct pairwise connections — so value rises with the square of users while link cost rises linearly. E-commerce splits into a taxonomy (B2C, B2B, G2C, C2C, P2P) that maps cleanly onto whether the traffic is client-server (a catalog order) or peer-symmetric (a C2C auction bid). The failure modes are concrete: a single server is a throughput and availability bottleneck (one bank server down for five minutes is catastrophic), while P2P trades that for discovery cost — a new BitTorrent peer must walk a bootstrap list to build a local index before it can fetch anything.

**Type:** Learn
**Languages:** Diagrams, standards
**Prerequisites:** Basic idea of a "process" and a "message"; this is an early Phase 1 lesson
**Time:** ~70 minutes

## Learning Objectives

- Distinguish the client-server model from peer-to-peer by *who initiates*, *who holds state*, and *how roles are assigned*, not by vague intuition.
- Trace a single request/reply exchange between a client process and a server process and name the messages crossing the network.
- Compute the value of a network of n users using Metcalfe's law (n(n-1)/2 connections) and explain why doubling users roughly quadruples value.
- Classify a real transaction into the B2C / B2B / G2C / C2C / P2P taxonomy and say whether it rides client-server or peer-symmetric mechanics.
- Identify the dominant failure mode of each model: server bottleneck/single-point-of-failure vs P2P bootstrap/discovery latency and free-rider load.
- Explain how a VPN lets geographically separate client and server processes behave as if they were on one LAN ("ending the tyranny of geography").

## The Problem

You join the IT team at a mid-size firm. A salesperson in New York complains: "The product catalog page from headquarters loads instantly, but when I pull live inventory from the Singapore warehouse it stalls or fails entirely." A second ticket: the engineering team wants to share large CAD design files among 40 laptops, and the central file server is melting under load every afternoon.

Both tickets are really *one* architectural question — which interaction model fits the workload, and where does that model break? The catalog is a textbook **client-server** request/reply that works because one server answers many clients. The Singapore inventory is the *same* model stretched across 15,000 km, which surfaces the model's coupling: client blocks on reply, so latency and any broken link become visible application stalls. The CAD-sharing problem is asking whether to keep funneling everything through one server (client-server) or let the 40 laptops exchange chunks directly (**peer-to-peer**). Picking wrong gives you either a melted server or a swarm nobody can find content on. This lesson gives you the vocabulary and the numbers to answer correctly.

## The Concept

Source material: `chapters/chapter-01-introduction.md`, sections "Business Applications" and "Home Applications".

### Why connect at all: resource sharing and the two goals

A network exists to make programs, equipment, and especially **data** available to anyone, regardless of physical location. The classic example is a shared high-volume printer: nobody needs a private printer, and one networked unit is cheaper, faster, and easier to maintain than a pile of desktop ones. But sharing *information* matters more than sharing hardware — a bank whose computers go down cannot survive five minutes; a computer-controlled assembly line, five seconds.

The second goal is about *people*, not data: email, VoIP (carrying phone calls over the data network), video conferencing, and desktop/document sharing where one worker's edit appears immediately on everyone else's screen. These two goals — resource sharing and human communication — map onto the two models below.

### The client-server model: request and reply

In the client-server model two **processes** (running programs) cooperate. Data lives on a powerful, centrally administered machine — the **server**. Users sit at simpler **client** machines. The interaction is strictly:

```
1. client process  --- Request --->  server process     (client now BLOCKS)
2. server process: look up / compute the requested work
3. client process  <--- Reply ----   server process     (client unblocks)
```

The defining property: **the client always initiates; the server only responds.** One server can handle hundreds or thousands of clients simultaneously. The Web is the canonical realization — your browser (client) sends a request to a Web server (server) which generates a page from its database. See [`assets/business-applications-to-home-applications.svg`](../assets/business-applications-to-home-applications.svg) for the request/reply timing on the left and the symmetric P2P mesh on the right.

| Property | Client-Server | Peer-to-Peer |
|---|---|---|
| Role assignment | Fixed (client vs server) | None — every node is both |
| Who initiates | Always the client | Anyone, either direction |
| State / data location | Centralized on server | Distributed across peers |
| Discovery | Known server address | Walk a bootstrap peer list |
| Scaling limit | Server CPU / bandwidth / availability | Free-riders; discovery cost |
| Examples | Web (HTTP), DNS, email retrieval | BitTorrent, online auctions, email at SMTP relay level |

### Peer-to-peer: no fixed clients or servers

In P2P, individuals form a loose group where everyone can, in principle, talk to everyone else; there is **no fixed division into clients and servers**. Many P2P systems (BitTorrent is the textbook case) keep **no central database of content**. Instead, each user maintains a local database and a list of nearby members. A new joiner bootstraps: go to any existing member, see what it has, collect names of *more* members, inspect those for more content and more names, and repeat. This walk is tedious for humans but trivial for computers — and it is exactly the cost you pay for eliminating the central server.

Note a subtlety the chapter highlights: email is "inherently peer-to-peer" at the relay level even though users *retrieve* mail via a client-server mailbox. The model you name depends on which hop you are looking at.

### Stretching the model across geography: VPNs

The client-server model does not care whether client and server share a building or sit 15,000 km apart. A salesperson in New York reaching a product-inventory database in Singapore uses the identical request/reply mechanics — but now the messages traverse the public Internet. A **VPN (Virtual Private Network)** joins the separate site networks into one extended network so the remote data behaves as if it were local. The chapter calls this *ending the "tyranny of geography."* The cost is that every property of the model (the client blocking on reply, sensitivity to a broken link) is now stretched over a high-latency path — which is exactly why the New York-to-Singapore inventory ticket stalls while the local catalog does not.

### Metcalfe's law: the value of being connected

Bob Metcalfe (inventor of Ethernet) hypothesized that a network's **value is proportional to the square of the number of users**, because that is roughly the number of distinct connections that can be made. The exact count of unordered pairs among n users is:

```
connections(n) = n * (n - 1) / 2          (a complete graph K_n)
```

Worked example:

| Users n | Pairwise connections n(n-1)/2 | Value vs n=10 |
|---|---|---|
| 10 | 45 | 1.0x |
| 20 | 190 | ~4.2x |
| 100 | 4,950 | ~110x |
| 1,000 | 499,500 | ~11,100x |

Doubling users from 10 to 20 multiplies connections from 45 to 190 — roughly 4x, the "square" effect. Link/port cost grows only linearly (n). This asymmetry is why connecting computers that "initially worked in isolation" was inevitable, and why the Internet's value exploded with its size. [`code/main.py`](../code/main.py) computes this table and contrasts it with linear cost.

### The e-commerce taxonomy and which model it rides

Doing business electronically splits into a small taxonomy. Crucially, each tag maps onto an interaction model:

| Tag | Full name | Example | Underlying model |
|---|---|---|---|
| B2C | Business-to-consumer | Ordering books online | Client-server (client = shopper) |
| B2B | Business-to-business | Carmaker ordering tires from a supplier | Client-server (automated client) |
| G2C | Government-to-consumer | Distributing tax forms electronically | Client-server |
| C2C | Consumer-to-consumer | Auctioning second-hand goods | **Peer-symmetric** (each consumer is buyer *and* seller) |
| P2P | Peer-to-peer | Music / file sharing | **Peer-to-peer** |

Online auctions are the instructive case: unlike traditional client-server e-commerce, consumers act as *both* buyers and sellers, so the traffic is peer-symmetric at the application level even when an auction site brokers it.

### Failure modes you can predict from the model

Because each model has a defining property, each has a predictable way to break:

- **Client-server — server bottleneck and single point of failure.** All state and load concentrate on the server. The melted CAD file server every afternoon is this: N clients each blocking on one server's finite CPU and bandwidth. If the server dies, *every* client is dead. (The bank that "could not last five minutes" is the availability version.)
- **Peer-to-peer — discovery latency and free-riders.** No central server means no central index: a fresh peer must walk the bootstrap list before it can fetch anything, so cold-start latency is real. And peers that download but never upload (free-riders) shift load onto the generous few, degrading the swarm.

Naming the model tells you which evidence to collect first: server CPU/queue depth and connection counts for client-server; peer count, bootstrap time, and upload/download ratio for P2P.

## Build It

The simulator in [`code/main.py`](../code/main.py) makes the two models concrete and runs entirely on the standard library.

1. Model a single **request/reply** exchange: a `ClientServerExchange` records the request message, the server's lookup, and the reply, printing the message sequence that crosses the network.
2. Model **P2P bootstrap discovery**: a small set of peers each hold a local content list and a neighbor list; `p2p_discover()` walks from a seed peer outward, accumulating known content and counting hops — exactly the "go to any member, get more names" process.
3. Compute **Metcalfe's law**: `metcalfe_connections(n)` returns n(n-1)/2 and `value_table()` prints the value-vs-cost comparison.
4. **Classify** transactions: `classify_ecommerce()` maps a (initiator, responder) pair onto B2C/B2B/G2C/C2C/P2P and reports the underlying model.

Run it:

```
python3 code/main.py
```

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Name the model for a given traffic flow | Who initiates; whether roles are fixed | You say "client-server" only when one side always initiates and holds state |
| Trace a request/reply | The two messages crossing the network and the client's blocked interval | You can point to the Request, the server work, and the Reply in order |
| Quantify network value | n(n-1)/2 vs n | Doubling users ~quadruples connections; you show the table |
| Classify an e-commerce transaction | Initiator/responder roles | A C2C auction is peer-symmetric; a B2C order is client-server |
| Predict the failure mode | Model's defining property | Client-server → server bottleneck; P2P → discovery cost / free-riders |

## Ship It

Produce one reusable artifact under `outputs/`:

- A one-page decision card: "client-server vs P2P" with the role/initiator/state checklist and each model's first-to-collect evidence.
- A Metcalfe's-law value calculator note with the n(n-1)/2 table for your real user counts.
- An e-commerce classification cheat sheet mapping the B2C/B2B/G2C/C2C/P2P tags to their underlying model.

Start from the program output: [`code/main.py`](../code/main.py) prints all three and can seed the artifact.

## Exercises

1. A home user loads a Wikipedia article, then their BitTorrent client fetches a Linux ISO. Name the model for each, and state who initiates and where the content index lives in each case.
2. Your firm has 30 offices that today each run an isolated LAN. Using Metcalfe's law, how many inter-office connections become possible if you join them all? If you add a 31st office, how many *new* connections appear?
3. The Singapore-inventory ticket: explain, in terms of the client blocking on reply, why a local catalog page loads instantly while the remote inventory stalls — and what role the VPN plays.
4. Classify each and give the underlying model: (a) a government tax-form portal, (b) a carmaker auto-ordering tires from a parts supplier, (c) two strangers bidding on a used camera, (d) a B2C bookstore checkout.
5. The CAD file server melts every afternoon under 40 laptops. Argue the case for switching that workload to P2P, and name the *new* failure mode you would now have to monitor.
6. Email is described as "inherently peer-to-peer," yet you check your inbox with a client-server mailbox. Resolve the apparent contradiction by naming which hop each statement describes.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Client-server model | "The normal way websites work" | A fixed-role pattern where the client *always* initiates request/reply and the server holds the data and only responds |
| Peer-to-peer (P2P) | "Illegal downloading" | A symmetric model with no fixed client/server roles and often no central content index; each peer is both requester and responder |
| Request / reply | "Asking the server something" | The two-message exchange where the client blocks after sending the request until the reply arrives |
| Server | "A big computer" | The process (and machine) that holds shared state and responds to client requests; a throughput and availability bottleneck |
| VPN | "Secure tunnel for privacy" | A virtual network joining separate sites so remote client/server processes behave as if on one LAN — "ends the tyranny of geography" |
| Metcalfe's law | "Networks get more valuable as they grow" | Value ~ n(n-1)/2, the count of distinct user pairs; value scales with the square of users while link cost scales linearly |
| C2C | "Online selling" | Consumer-to-consumer; peer-symmetric because each consumer is simultaneously buyer and seller (auctions) |
| Bootstrap / discovery | "Joining the swarm" | The walk a new P2P peer makes through a known member to collect content lists and more member names before it can fetch |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 1, Section 1.1 ("Uses of Computer Networks").
- RFC 2616 / RFC 7230-7235 — HTTP, the canonical client-server request/reply protocol (request line, methods, status replies).
- RFC 5321 — SMTP, the mail relay protocol that makes email "inherently peer-to-peer" between mail servers.
- RFC 4271 — BGP, and RFC 4364 — BGP/MPLS IP VPNs, for how site networks are joined into one extended network.
- "BitTorrent" — Bram Cohen, *Incentives Build Robustness in BitTorrent* (2003), for the P2P discovery and free-rider problem.
- George Gilder, "Metcalfe's Law and Legacy," *Forbes ASAP* (1993), for the original n-squared value argument.
