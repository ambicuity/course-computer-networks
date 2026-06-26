# Chord DHT Finger Tables and Successor Ring

> Read the protocol, build the evidence, then ship an artifact you can reuse in real troubleshooting.

**Type:** Learn
**Languages:** Python, diagrams
**Prerequisites:** Lesson 07 (Peer-to-peer Networks), earlier lessons in Phase 13
**Time:** ~75 minutes

## Learning Objectives

- Explain section 7.5.4 (DHTs / Chord) in operational terms
- Identify the identifier ring, successor function, and finger table entries that prove a lookup
- Connect the mechanism to at least one realistic failure mode (linear scan, stale finger, node churn)
- Produce a reusable simulator that builds finger tables and performs O(log n) lookups

## The Problem

A peer-to-peer network with no central tracker must still answer one question: "which peer has the content I want?" A central index is simple but is a bottleneck and a single point of failure; having every peer keep a full index is too expensive to maintain as content moves. The research question of 2001 was whether a fully distributed index could perform well: each node keeps little state, lookups are fast, and the system scales as nodes join and leave.

Chord is one answer. It turns the index into a hash table spread across a ring of nodes, and it uses a finger table per node to cut the lookup path from O(n) (linear walk around the ring) down to O(log n).

## The Concept

Source material: [`chapters/chapter-07-the-application-layer.md`](../../../../chapters/chapter-07-the-application-layer.md) section `7.5.4` (Peer-to-Peer Networks, DHTs / Chord).

A Chord DHT consists of `n` participating nodes. Each node and each content key is mapped to an `m`-bit identifier using a hash function (Chord uses SHA-1, giving `m = 160`; the source illustrates with `m = 5`). Identifiers are arranged in ascending order into a ring modulo `2^m`.

The core function is `successor(k)`: the identifier of the first actual node at or following `k` clockwise around the ring. For example, with actual nodes `{1, 4, 7, 12, 15, 20, 27}` and `m = 5`: `successor(6) = 7`, `successor(8) = 12`, `successor(22) = 27`.

A key is produced by hashing the content name: `key = hash(content)`. To store a `(key, value)` pair, a node asks `successor(key)` to hold the value. To look up a key, a node must find `successor(key)`.

### Linear lookup (the slow baseline)

The simplest scheme: each node knows only its immediate successor. A lookup is forwarded around the ring until it reaches `successor(key)`. The mean number of hops is `n/2`, which is unacceptable for millions of nodes.

### Finger tables (the fast path)

Each node maintains a finger table with `m` entries, indexed `0` through `m-1`. For a node with identifier `k`, entry `i` is:

```text
start   = (k + 2^i) mod 2^m
succ    = successor(start)
```

So entry `i` points to the node responsible for the identifier `k + 2^i`, giving the node a long-distance pointer that doubles in distance each step. Using the finger table, a lookup at node `k` for `key` proceeds:

1. If `key` lies between `k` and `successor(k)`, the answer is `successor(key)`; terminate.
2. Otherwise, find the finger-table entry whose `start` is the closest predecessor of `key`, and forward the query to that node's IP. That node is closer to `key` and repeats the process.
3. Because each hop at least halves the remaining distance to the target, the average number of lookups is `log n`.

### Worked example from the source

With nodes `{1, 4, 7, 12, 15, 20, 27}` and `m = 5`:

- Lookup `key = 3` at node 1: 3 lies between 1 and successor(1)=4, so the answer is node 4. One hop.
- Lookup `key = 16` at node 1: 16 is not between 1 and 4. The closest finger-table predecessor of 16 is 9, whose successor is node 12. Forward to node 12. Node 12's closest predecessor of 16 is 14, whose successor is node 15. Forward to node 15. Node 15 sees 16 lies between it and its successor 20, so it returns node 20. Three hops -- far below the `n/2 = 3.5` linear average, and consistent with `log n` scaling.

### Working Model

```text
content name -> hash -> key (m-bit identifier)
                          |
                          v
node k receives lookup(key)
                          |
            +-------------+-------------+
            |                           |
   key in (k, successor(k)]?         finger table: pick largest
   -> answer is successor(key)          start <= key, forward there
                                       (halves remaining distance)
                          |
                          v
answer: successor(key) in O(log n) hops
```

## Build It

This lesson ships a simulator (`code/main.py`) that implements a Chord ring with `m = 6` (64 identifiers). It builds the finger table for every node, performs both linear and finger-accelerated lookups, and prints the hop count for each so you can see the `O(log n)` vs `O(n)` difference directly.

Run it:

```bash
python3 code/main.py
```

The simulator lets you:

1. Build a ring of 8 nodes and print every node's full finger table.
2. Look up keys using the linear (successor-walk) path and the finger-table path, and compare hop counts.
3. Inject a node failure and observe that lookups still succeed via the live successor.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Locate the layer | Finger-table dumps, lookup hop counts, successor pointers | You can explain why a failed lookup is an index/ring issue, not a transport issue |
| Explain normal behavior | Ring diagram plus finger tables plus a clean lookup trace | Finger hops stay near `log n`; linear hops average `n/2` |
| Diagnose abnormal behavior | Stale finger pointing at a departed node, churn trace | The hypothesis (stale finger, node left without notifying) predicts the extra hop or failure |

## Ship It

Create one artifact under `outputs/`:

- A one-page runbook for diagnosing a stale-finger lookup failure
- A finger-table worksheet (compute the table for a given node and ring by hand)
- The simulator from `code/main.py` extended with node-join stabilization
- A study prompt that teaches Chord from the simulator output

Start with [`outputs/prompt-chord-dht-finger-tables.md`](../outputs/prompt-chord-dht-finger-tables.md).

## Exercises

1. Using the ring `{1, 4, 7, 12, 15, 20, 27}` with `m = 5`, compute the finger table for node 4 by hand, then verify it against the simulator.
2. Look up `key = 16` at node 1 using the finger-table path. List each hop and confirm the hop count is `O(log n)`.
3. Compare the linear and finger-table hop counts for 100 random lookups. What is the ratio? Does it match `log n / (n/2)`?
4. A node leaves the ring without updating its predecessor's finger table. Describe the observable failure and the smallest fix (successor-list stabilization).
5. Why does Chord use a hash function (SHA-1) to map both node addresses and content names into the same identifier space?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| DHT | A distributed database | A distributed hash table that maps keys to values across nodes with no central index |
| Chord | A P2P protocol | A DHT that arranges identifiers on a ring and uses finger tables for O(log n) lookups |
| successor(k) | The next node | The first actual node at or after identifier k, clockwise around the ring |
| Finger table | A routing table | Per-node table of m entries; entry i points to successor(k + 2^i), giving exponentially spaced long-distance pointers |
| Identifier ring | A circle | The m-bit identifier space [0, 2^m) arranged modulo 2^m, on which nodes and keys are placed by hashing |

## Further Reading

- The full source chapter linked above, section 7.5.4
- Stoica et al., "Chord: A Scalable Peer-to-peer Lookup Service for Internet Applications" (2001)
- RFC 7695 and Kademlia for a related DHT used in practice
