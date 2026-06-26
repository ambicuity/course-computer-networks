# Peer-to-Peer Networks

> Not everyone can set up a 1,000-node CDN. P2P (Peer-to-Peer) networks pool the resources of every participant so the system grows with the demand, not against it. The textbook's worked example: N users each on a 1 Mbps symmetric link give an *aggregate* upload capacity of N Mbps, and a binary-tree pipelining construction can use that capacity to disseminate a file in O(log N) rounds. The two practical P2P protocols are **BitTorrent** (Cohen, 2001) — the most popular P2P protocol in history, with a *torrent metafile* containing 160-bit SHA-1 hashes of each chunk, a centralized or DHT-based *tracker* that maintains the swarm, *rarest-first* piece selection to keep all pieces equally available, and a *tit-for-tat choking algorithm* that rewards uploaders — and **Chord** (Stoica et al., 2001), a *Distributed Hash Table* that places nodes on a 160-bit ring and provides `O(log N)` lookups via a finger table. BitTorrent won the P2P wars for content delivery; Chord (and Kademlia, Maymounkov & Mazières 2002) won the DHT wars for the tracker replacement that BitTorrent needs to be fully decentralized. This lesson builds a BitTorrent-style rarest-first piece selector, a tit-for-tat swarm simulator, a Chord ring with successor lookup, and a download-time scaling experiment that proves the textbook's "self-scaling" claim.

**Type:** Build
**Languages:** Python
**Prerequisites:** Hash functions, asymptotic complexity (O(log N)), the previous lessons on content traffic and CDNs
**Time:** ~90 minutes

## Learning Objectives

- Trace the BitTorrent content-distribution path: get torrent metafile → contact tracker → join swarm → trade chunks rarest-first with tit-for-tat reciprocity.
- Implement rarest-first piece selection and explain why it prevents the seeder-bottleneck failure mode of sequential downloading.
- Implement tit-for-tat choking with an optimistic unchoke slot and run a multi-round swarm simulation to completion.
- Build a Chord DHT ring on a 2^m identifier space, implement successor lookup, and run the textbook's worked example of a 3-step lookup at node 1 for key 16.
- Estimate how download time scales with swarm size, and connect the empirical result to the textbook's "binary-tree pipelining" argument.
- Identify the difference between *structured* (Chord, Kademlia) and *unstructured* (early Gnutella) P2P networks, and the trade-off each makes.

## The Problem

It is 2003. You are an early employee at a small startup with one server and a 100 Mbps link. You have just been served a Digital Millennium Copyright Act takedown notice for hosting a popular album that 200,000 people want to download. You have three options:

- Option A: Take the file down. Lose the user base. (Bad.)
- Option B: Buy more bandwidth. At 200,000 downloads * 60 MB = 12 PB of total transfer, this would cost more than your entire company is worth. (Worse.)
- Option C: Have the *users* host the file for each other. Every downloader becomes a uploader; the aggregate bandwidth grows with the user base. (This is the P2P insight.)

Option C is the foundational idea of peer-to-peer file sharing. Napster (1999–2001) proved the model worked at 50 million users; the courts shut it down because the *centralized index* (the catalog of who-has-what) was a single point of legal liability. BitTorrent, which appeared in 2001, learned from Napster's failure and moved the index into a *torrent metafile* distributed via Web search and into a *tracker* that the operator could plausibly disclaim. By 2003, P2P was the majority of Internet traffic; by 2007, BitTorrent alone carried a third of all upstream bytes in some regions.

But the tracker is still a single point of failure and of legal pressure. So the research community asked: can we build a tracker that is *itself* distributed? That is the question Distributed Hash Tables (DHTs) answer, and Chord is the canonical solution. Modern BitTorrent uses a Kademlia-based DHT (the *Mainline DHT*) as a tracker replacement, and the BEP-5 specification describes it.

## The Concept

### The P2P capacity argument

The textbook's argument is the cleanest case for P2P. Consider N users, each with 1 Mbps upstream and 1 Mbps downstream. The aggregate upstream capacity is N Mbps. A naïve centralized server has at most some fixed C Mbps of upstream, and it cannot serve N users at 1 Mbps each when N > C. The same N users, sharing with each other, can serve the file to everyone at 1 Mbps each.

The textbook's pipeline construction: arrange the N users in a binary tree, with each non-leaf user sending to two other users. The file is split into 1000 pieces. Each non-leaf user receives a piece from above and sends the previously-received piece downward, simultaneously. After a small number of pieces equal to the depth of the tree (log_2 N), all non-leaf users are busy uploading. There are roughly N/2 non-leaf users, each uploading 1 Mbps, so the aggregate throughput is N/2 Mbps. A second tree with the leaves and non-leaves swapped uses the other N/2 Mbps.

The net result: P2P is *self-scaling*. The capacity grows with the user base, while a centralized server's capacity is fixed. The textbook calls this "always 'large enough' in some sense."

The textbook is careful to note that this is a back-of-the-envelope argument. In practice, users have asymmetric links (ADSL gave 1 Mbps up but 8 Mbps down), and the binary-tree construction assumes perfectly synchronized scheduling. Real BitTorrent does not achieve the theoretical O(log N) dissemination, but it does achieve O(N / log N) throughput, which is *vastly* better than the O(1) of a centralized server.

### BitTorrent: the three problems

The textbook identifies three problems that any P2P content-distribution protocol must solve:

1. **Discovery** — how does a peer find other peers that have the content it wants?
2. **Replication** — how is content replicated fast enough that everyone gets good throughput?
3. **Incentive** — how do you prevent *free-riding* (peers that download but do not upload)?

BitTorrent's answers:

**Discovery (the torrent metafile and the tracker).** Every shared file has a *torrent metafile* — a small (~50 KB) file containing:
- The **tracker URL** (the IP/port of the server that tracks this swarm).
- A list of **pieces** the file is split into (typically 64 KB to 512 KB each), with the **160-bit SHA-1 hash** of each piece.

The metafile is published on a Web site, indexed by search engines, or shared on a tracker aggregator. A peer that wants to download starts by fetching the metafile, then contacts the tracker. The tracker maintains a list of *active peers* in the swarm (peers that have checked in within the last ~30 minutes). New peers learn about other peers from the tracker.

**Replication (rarest-first piece selection).** If everyone requested piece 1 first, then piece 2, then piece 3, every peer would depend on the initial seed for the same piece at the same time — the seed would be a bottleneck. Instead, BitTorrent peers request the *rarest* missing piece available in the swarm. Rarest-first has two benefits: (1) it makes new copies of scarce pieces, raising their swarm-wide availability; (2) it evens out the load across sources. After a few rounds, every piece is widely replicated and no single peer is a bottleneck.

**Incentive (tit-for-tat choking).** A BitTorrent peer maintains TCP connections to ~30–80 other peers. Every ~10 seconds, it *unchokes* (allows uploads to) the 4 peers that have sent it the most bytes recently. This is tit-for-tat: upload to those who upload to you. The fifth unchoke slot is given to a *random* peer (*optimistic unchoke*) so that new peers can bootstrap into the swarm. Peers that do not upload are *choked* (have their uploads stopped).

The textbook is careful to note that tit-for-tat is not cryptographically secure. Sophisticated clients can game the system (Piatek et al., 2007), and the *optimistic unchoke* is an open door. But the system is good enough that free-riders get measurably worse performance, and most users do not bother to cheat.

### DHTs and Chord

The tracker is the single point of failure. To decentralize it, BitTorrent uses a DHT. The textbook introduces the four DHTs invented in 2001 — **Chord**, **CAN**, **Pastry**, and **Tapestry** — and explains Chord in detail.

A **DHT (Distributed Hash Table)** is a key-value store spread across many nodes, with no central coordinator. The keys and node IDs are hashed into the same m-bit space (typically m = 160, using SHA-1). The basic API is:

- `put(key, value)` — store a value at the node responsible for `key`.
- `get(key)` — retrieve the value at the node responsible for `key`.

**Chord** is the simplest of the four. It arranges the 2^m identifiers in a *ring*. Each node is responsible for the keys that hash to its own ID and the IDs of its *predecessor*. The node responsible for a key is the *successor* of the key — the first node clockwise on the ring from the key's ID.

A lookup is `O(N)` in the worst case if you walk the ring one step at a time. To speed it up, each node maintains a **finger table** with m entries. Entry `i` at node `k` is the IP address of the node responsible for `start_i = k + 2^i (mod 2^m)`. With this table, a lookup at node `k` for key `K`:

- If `K` is between `k` and `successor(k)`, return `successor(k)`.
- Otherwise, find the entry whose `start_i` is the largest predecessor of `K`, and forward the query there.

Each step at least halves the remaining distance to `K`, so the lookup is `O(log N)`.

The textbook's worked example: m=5, nodes at 1, 4, 7, 12, 15, 20, 27. Look up key 16 from node 1. Node 1 finds that 16 is not in [1, 4], so it consults the finger table, finds the closest predecessor (9), and forwards to the IP of node 12. Node 12 finds that 16 is not in [12, 15], so it consults its finger table, finds the closest predecessor (14), and forwards to the IP of node 15. Node 15 finds that 16 is in [15, 20], so it returns 20. Three steps for 27 nodes, and the next step would be 2^5 = 32 ≈ 27.

### Why a DHT, why a torrent

DHTs and BitTorrent solve different problems and are usually composed. The torrent metafile says *what* is being shared (a hash of the file's pieces). The tracker (or DHT) says *who* is sharing it (a list of peer IPs). The rarest-first + tit-for-tat mechanism decides *which* peer to fetch from and *when*. The textbook's Figure 7-70 shows this composition: get metafile → get peers from tracker → trade chunks.

In modern BitTorrent (BEP-5, the "Mainline DHT"), the tracker is replaced by a Kademlia DHT. Each BitTorrent client both serves *and* consumes DHT entries; the swarm is discovered by `get(infohash)` on the DHT, and the contact peers' IPs come back as the value. This makes the system entirely serverless — there is no operator to sue.

### The privacy story

The textbook notes that P2P has a privacy advantage over centralized content delivery. In a CDN, the provider sees every request and can build a profile of every user. In a P2P network, no single peer sees the whole system; the privacy guarantees are weaker (you can see what your *neighbors* are downloading) but they are *different*. This is the argument for "decentralized" systems that has driven the recent interest in P2P for messaging (Briar), file sharing (IPFS), and video (PeerTube).

## Build It

We will use the existing `code/main.py` which implements five self-contained functions:

1. **Rarest-first piece selection** — `rarest_first_piece(peer, peers, total_pieces)` returns the rarest missing piece available in the swarm. Run the demo to see `peer-01` pick piece 0 or 1 (each held by 1 of 3 other peers) over piece 2 (held by 3 of 3).
2. **Tit-for-tat swarm simulation** — `simulate_swarm_round()` runs one round of uploads and downloads, with each peer picking 4 upload candidates (3 by reciprocity + 1 optimistic). `run_swarm()` runs many rounds until all peers are complete or 30 rounds elapse.
3. **Chord DHT successor lookup** — `ChordRing(bits=6)` creates a 2^6 = 64-node ring. `add_node(id)` adds a node. `successor(key)` returns the next node clockwise.
4. **Download-time scaling** — `download_time_scaling()` simulates 1 to 8 peers downloading a 50 MB file at 2 Mbps each, and reports the estimated time. The result should fall as peers join, demonstrating self-scaling.
5. **State table** — `swarm_state_table()` prints an ASCII table of which peer has how many pieces.

Steps:

1. Read textbook section 7.5.4 ("Peer-to-Peer Networks"). Pay attention to the binary-tree argument and the Chord worked example in Figure 7-71.
2. Open `code/main.py` and look at `rarest_first_piece()`. Note that the `Counter` is built from pieces that *someone else* has and the *chooser* is missing; the min-count piece is then picked at random among ties.
3. Run `python3 code/main.py`. The output has 5 sections demonstrating each of the five ideas.
4. In `download_time_scaling()`, change `max_peers=8` to `max_peers=16` and re-run. Does the time keep falling, or does it plateau? (The 5% overhead per peer eventually dominates.)
5. In `ChordRing(bits=6)`, change to `bits=8` (256-node ring). Add more nodes and verify that `successor()` returns the right answer across the wrap-around at 0.

## Use It

| API call | What it does | Typical output |
|---|---|---|
| `Peer(peer_id, pieces=set(), upload_slots=4)` | Create a peer in a swarm | Peer instance |
| `rarest_first_piece(peer, peers, total_pieces)` | Pick the rarest missing piece | int (piece index) or None |
| `simulate_swarm_round(peers, total_pieces)` | Run one round of tit-for-tat trading | dict of transfers |
| `run_swarm(peer_count, total_pieces, seed=42)` | Run the swarm to completion | (peers, rounds_used) |
| `ChordRing(bits=6)` | Create a 64-node Chord ring | — |
| `ring.add_node(id)` | Add a node to the ring | None |
| `ring.successor(key)` | Find the first node clockwise of `key` | int node ID or None |
| `download_time_scaling(total_pieces, file_size_mb, upload_mbps, max_peers=8)` | Estimate scaling with swarm size | dict of peer count → seconds |
| `swarm_state_table(peers, total_pieces)` | Print ASCII state of the swarm | string |

The output of `download_time_scaling(total_pieces=20, file_size_mb=50.0, upload_mbps=2.0, max_peers=8)` shows the time falling from ~250 s for 1 peer to ~30 s for 8 peers, demonstrating the textbook's self-scaling claim.

## Ship It

The deliverable is the lesson folder:

```
phases/13-streaming-real-time-media-and-content-delivery/07-peer-to-peer-networks/
├── assets/
│   └── peer-to-peer-networks.svg
├── code/
│   └── main.py
├── docs/
│   └── en.md
├── notebook/
│   └── notes.md
├── outputs/
│   └── trace.json
└── quiz.json
```

To prove the lesson works:

1. `python3 code/main.py` — must print all 5 sections without errors.
2. `python3 -m py_compile code/main.py && echo OK` — must print `OK`.
3. Open `assets/peer-to-peer-networks.svg` in a browser.

## Exercises

1. **Rarest-first vs sequential.** Modify `rarest_first_piece()` to use *sequential* selection (always pick the lowest missing piece). Run a 6-peer simulation with 20 pieces. How many more rounds are needed for completion? (Answer: sequential takes ~3-5× longer because all peers wait on the seed for the first few pieces.)
2. **Tit-for-tat with no optimism.** Remove the optimistic unchoke slot in `upload_candidates()`. A new peer joining an empty swarm will be choked by everyone and *never* get a first piece. Verify this by initializing a swarm with 5 peers, none of which has the seed, and checking that the simulation stalls.
3. **Chord lookup path.** Add a `lookup_path()` method to `ChordRing` that returns the list of nodes visited during a `successor()` walk. With nodes at `[1, 4, 7, 12, 15, 20, 27]`, look up key 16 from node 1 and confirm the path is `[1, 12, 15, 20]`. Look up key 3 from node 1 and confirm the path is `[1, 4]`. Look up key 0 from node 27 and confirm the path is `[27, 1]`.
4. **Finger table entries.** Write a `finger_table(node_id, nodes, bits)` function that returns the m finger entries for a node. Verify with the textbook's Figure 7-71(b): node 1's finger table should be `[(1, 4), (3, 4), (5, 7), (9, 12), (17, 20)]` (each entry is `(start, successor_IP_node)`).
5. **Asymmetric links.** In the textbook's worked example, every user has 1 Mbps up *and* 1 Mbps down. In a realistic ADSL deployment in 2007, the upstream was 1 Mbps and the downstream was 8 Mbps. Re-derive the binary-tree construction. Does the system still scale? (Answer: yes, but the bottleneck shifts to the upstream tree. The downstream is plentiful; the upstream is scarce. The optimal strategy is to *not* upload to multiple peers, but to concentrate uploads on the peer with the fastest downstream to you, then download from many.)
6. **The "free rider" problem.** Simulate a swarm of 10 peers, 9 of which use tit-for-tat and 1 of which only downloads and never uploads. After 30 rounds, does the free-rider have the full file? (Answer: in the implementation above, yes — because the free-rider is *randomly* picked by the optimistic unchoke slot with probability 1/4. A real BitTorrent client could choke the free-rider, but the optimistic unchoke makes this difficult. The textbook notes that BitTorrent "does not prevent clients from gaming the system in any strong sense.")

## Key Terms

| Term | Meaning |
|---|---|
| Peer | A computer in a P2P network; alternately acts as client and server |
| Swarm | All peers currently sharing a specific file |
| Seeder | A peer with the complete file |
| Leecher / free-rider | A peer that downloads but does not upload |
| Torrent metafile | A small file containing the tracker URL and piece hashes |
| Piece | A chunk of a shared file, typically 64 KB to 512 KB |
| SHA-1 hash | 160-bit cryptographic hash of each piece; verifies integrity |
| Tracker | A server that maintains the list of active peers in a swarm |
| Rarest-first | A piece-selection strategy that fetches the least-replicated piece first |
| Tit-for-tat | A reciprocity strategy: upload to peers that upload to you |
| Optimistic unchoke | A random unchoke slot that lets new peers bootstrap into the swarm |
| Choking | Stopping uploads to a peer (typically because they do not upload back) |
| DHT | Distributed Hash Table; a key-value store spread across many nodes |
| Chord | A specific DHT that places nodes on a ring and uses finger tables for O(log N) lookups |
| Finger table | The m-entry routing table at each Chord node |
| Successor | The first node clockwise of a key on the Chord ring |
| Kademlia | A DHT based on XOR distance; the basis of BitTorrent's Mainline DHT |
| Mainline DHT | The Kademlia-based DHT used by BitTorrent (BEP-5) |
| Self-scaling | The P2P property that aggregate capacity grows with the user base |
| BEP | BitTorrent Enhancement Proposal; the standards-track documents for the protocol |
| Tracker scrape | An HTTP request to a tracker to get the full peer list; used for swarm statistics |

## Further Reading

- **Cohen, B. (2003)** — "Incentives Build Robustness in BitTorrent" *P2P-Econ '03*. The original BitTorrent design paper.
- **Stoica, I., Morris, R., Karger, D., Kaashoek, M. F., & Balakrishnan, H. (2001)** — "Chord: A Scalable Peer-to-Peer Lookup Service for Internet Applications" *SIGCOMM '01*. The Chord paper.
- **Maymounkov, P. & Mazières, D. (2002)** — "Kademlia: A Peer-to-Peer Information System Based on the XOR Metric" *IPTPS '02*. The Kademlia paper; the basis of the Mainline DHT.
- **Piatek, M., Isdal, T., Anderson, T., Krishnamurthy, A., & Venkataramani, A. (2007)** — "Do Incentives Build Robustness in BitTorrent?" *NSDI '07*. The paper that showed BitTorrent's tit-for-tat is gameable.
- **Saroiu, S., Gummadi, P. K., & Gribble, S. D. (2003)** — "Measuring and Analyzing the Characteristics of Napster and Gnutella Hosts" *Multimedia Systems*. The paper that measured the free-rider problem in early P2P.
- **BEP-3** — The BitTorrent Protocol Specification. The canonical protocol document at `www.bittorrent.org/beps/bep_0003.html`.
- **BEP-5** — The Mainline DHT Specification. The Kademlia-based DHT used by modern BitTorrent clients.
- **Peterson, L. & Davie, B.** — *Computer Networks: A Systems Approach*, section 7.5.4. The textbook this lesson series is built from.
