# Limited-Contention Protocols

> Pure contention (ALOHA, CSMA) wins at low load because collisions are rare and delay is near zero, but it collapses at high load: the success probability of a symmetric slotted scheme is `k·p·(1−p)^(k−1)`, maximized at `p = 1/k`, which decays toward the asymptote `1/e ≈ 0.368` once five or more stations are ready. Collision-free protocols (bit-map reservation, binary countdown) do the reverse — high fixed overhead at low load, near-100% efficiency at high load. Limited-contention protocols bridge the two by splitting `N` stations into groups so only one group contends per slot, shrinking the contention size `k` toward the left edge of the acquisition curve. The canonical instance is the **Adaptive Tree Walk Protocol** (Capetanakis, 1979), modeled on the WWII Dorfman group-testing scheme: stations are leaves of a binary tree, slot 0 lets the root contend, and on collision the search recurses depth-first into the left then right child. Under load estimate `q`, the optimal starting level is `i = log₂(q)`, where the expected `2^(−i)·q` contenders per node equals 1, and provably-empty subtrees (siblings after an idle probe) are pruned to save slots.

**Type:** Build
**Languages:** Python, models
**Prerequisites:** Slotted ALOHA, CSMA/CD, collision-free protocols (bit-map, binary countdown) from earlier Phase 5 lessons
**Time:** ~90 minutes

## Learning Objectives

- Derive why a symmetric contention slot maximizes success at `p = 1/k` and why throughput drops to `1/e` as `k` grows past ~5.
- Trace one full run of the Adaptive Tree Walk Protocol on an 8-leaf tree, naming which node owns each contention slot and why collisions trigger a depth-first descent.
- Compute the optimal starting level `i = log₂(q)` from a ready-station estimate `q` and explain what that does to delay at low versus high load.
- Apply the two pruning rules (idle-subtree stop, guaranteed-collision skip) and count the slots saved on a concrete ready set.
- Run `code/main.py` to simulate the tree walk and produce a per-slot trace (node, outcome, contenders) that you can annotate as evidence.

## The Problem

You are sizing a shared-medium control bus — think a satellite uplink slot, a sensor field reporting over one RF channel, or a legacy token-style backplane — where the number of stations with something to send swings wildly. At 3 a.m. two of 256 nodes are active; at the 9 a.m. shift change 120 are. If you hard-wire pure slotted ALOHA, the morning peak thrashes: at `k = 120` contenders the per-slot success probability is `120·(1/120)·(1−1/120)^119 ≈ 0.368`, so roughly 63% of slots are wasted on idle gaps and collisions, and offered load above `1/e` drives the channel into congestive collapse. If instead you hard-wire a collision-free bit-map that gives every one of 256 stations a reservation bit each cycle, the 3 a.m. trickle pays 256 bits of overhead to send 2 frames — delay is dominated by scanning empty reservation slots.

Neither static choice is right. You need a protocol whose *effective contention group size* tracks the live load: many stations per slot when quiet, one station per slot when busy. That is exactly what limited-contention protocols deliver, and the tree walk gives you a concrete, implementable knob — the starting level — tied to a measurable input, `q`.

## The Concept

### The two regimes you are trying to merge

| Property | Contention (slotted ALOHA / CSMA) | Collision-free (bit-map, binary countdown) |
|---|---|---|
| Delay at **low** load | Low — transmit almost immediately | High — must wait through reservation overhead |
| Efficiency at **high** load | Poor — collisions dominate, peaks at `1/e` | High — fixed overhead amortizes, approaches 1.0 |
| Overhead source | Collisions and idle slots scale with `k` | Reservation/countdown bits, fixed per cycle |
| Failure mode | Congestive collapse above `G ≈ 1` | Wasted slots scanning silent stations |

A limited-contention protocol uses contention semantics but *restricts who may contend in any given slot*, so it inherits ALOHA's low delay when few stations are active and approaches collision-free efficiency when many are.

### Why symmetric contention caps at 1/e

With `k` ready stations each transmitting in a slot with probability `p`, exactly one succeeds when one transmits (`p`) and the other `k−1` defer (`(1−p)^(k−1)`), summed over the `k` stations:

```
Pr[success] = k · p · (1 − p)^(k − 1)
```

Differentiating and solving gives the optimal `p* = 1/k`. Substituting back:

```
Pr[success | p*] = (1 − 1/k)^(k − 1)  →  1/e ≈ 0.368  as k → ∞
```

For `k = 2` this is 0.5; by `k = 5` it has already fallen to ≈0.41 and keeps creeping toward 0.368. The lesson: the only way to raise per-slot success is to **lower the competition `k`**, not to retune `p`. `code/main.py` prints this curve so you can see the cliff. The accompanying SVG (`assets/limited-contention-protocols.svg`) plots the same acquisition curve next to the tree.

### Grouping: trading bit-map length for collision risk

Limited-contention protocols partition stations into (not necessarily disjoint) groups; only group 0 contends in slot 0, group 1 in slot 1, and so on. The group *size* is the design dial:

- **One station per group** → never collides (it degenerates to binary countdown), but the scan to give everyone a turn is `N` slots long.
- **Two stations per group** → collision probability per slot is `p²`, negligible for small `p`, and the scan halves.
- **All stations in one group** → pure slotted ALOHA again.

So small groups buy collision-freedom at the cost of a long scan; large groups buy a short scan at the cost of collisions. The art is making the group size **dynamic**: large when load is low, down to one when load is high.

### The Adaptive Tree Walk Protocol

The cleanest way to assign stations to slots dynamically is Capetanakis's tree walk, structurally identical to Dorfman's 1943 WWII syphilis blood-pooling test: pool `N` samples, test once; if clean, declare all healthy; if positive, split into two halves and recurse.

Picture `N` stations as the leaves of a binary tree (see `assets/limited-contention-protocols.svg`). Number nodes breadth-first: node 1 is the root, nodes 2–3 the next level, 4–7 the leaves' parents, and so on. The protocol runs immediately after each successful frame:

1. **Slot 0 → node 1 (root):** every station may contend.
2. If **exactly one** transmits → success, channel acquired, done.
3. If the slot is **idle** → no station under that node is ready; stop searching this subtree.
4. If there is a **collision** → recurse: next slot belongs to the node's **left child**, then (after that subtree resolves) the **right child**.

In effect, a root collision triggers a **depth-first search** of the tree to enumerate every ready station, one contention slot per visited node.

### Worked trace: stations A–H, only C and E ready

Leaves are A B C D E F G H under parents 4(A,B) 5(C,D) 6(E,F) 7(G,H); 2 covers A–D, 3 covers E–H.

| Slot | Node probed | Stations under node | Outcome | Action |
|---|---|---|---|---|
| 0 | 1 | A–H | Collision (C,E) | Descend to left child 2 |
| 1 | 2 | A–D | Single (C) | **C transmits** — subtree done |
| 2 | 3 | E–H | Single (E) | **E transmits** — subtree done |

Two ready stations resolved in three contention slots. Had all eight been ready, the walk would visit far more nodes — which is the point of starting lower under heavy load.

### Adaptive starting level: i = log₂(q)

Under heavy load it is wasteful to dedicate slot 0 to the root, because the root resolves cleanly only in the unlikely event that *exactly one* station is ready. Each node at level `i` (root = level 0) covers a fraction `2^(−i)` of stations, so if `q` stations are ready and uniformly spread, a level-`i` node holds an expected `2^(−i)·q` of them. You want about **one contender per slot**, i.e. `2^(−i)·q = 1`, which solves to:

```
i = log₂(q)
```

Estimate `q` by monitoring recent traffic, then skip directly to level `⌊log₂ q⌋` and run the walk across that level's nodes. Low load → small `q` → start near the root (large groups, ALOHA-like low delay). High load → large `q` → start deep (groups of ~1, collision-free-like efficiency). This single knob is what makes the protocol *adaptive*.

### Two pruning optimizations

Improvements over the basic walk (Bertsekas & Gallager, 1992) cut wasted probes:

- **Idle-subtree stop:** if a node's slot is idle, no station beneath it is ready — never probe its children.
- **Guaranteed-collision skip:** if node 1 collided and node 2 then came up idle, node 3 is *guaranteed* to collide (≥2 ready stations exist, none under 2, so all are under 3). Skip the redundant probe of 3 and descend straight to 6.

Example: only G and H ready. Node 1 collides → node 2 idle → **skip node 3** → node 6 idle → **skip node 7** → probe node G's parent, then G, then H. `code/main.py` implements both rules and reports slots saved.

## Build It

1. Read `code/main.py`: it builds a binary tree over `N` leaves, marks a chosen ready set, and walks the tree depth-first emitting one row per contention slot.
2. Run `python3 main.py` from the `code/` directory. Confirm the symmetric-success table shows the drop toward 0.368 and the tree-walk trace matches the A–H worked example.
3. Change the ready set (e.g. `{ "G", "H" }`) and verify the pruning log reports the skipped guaranteed-collision node.
4. Set a heavy ready set (e.g. 12 of 16 stations) and pass an estimated `q`; check that the optimal starting level prints as `⌊log₂ q⌋` and the walk begins at that level.
5. Save a trace you find instructive into `outputs/` as your annotated evidence artifact.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Identify the regime | Measured `q` (ready stations) and per-slot outcomes | You can say whether contention or collision-free dominates and why |
| Justify the start level | `i = log₂(q)` computation vs. observed contenders/slot | Starting level keeps mean contenders per slot near 1 |
| Read a tree-walk trace | Per-slot (node, contenders, outcome: idle/single/collision) | Every collision is followed by a left-then-right descent; every idle stops a subtree |
| Spot a pruning opportunity | A collision followed by an idle sibling | You can name the guaranteed-collision node and skip it |
| Compare to neighbors | ALOHA `1/e` cap vs. bit-map fixed overhead | You explain when each static protocol beats the adaptive walk |

## Ship It

Create one artifact under `outputs/`:

- An annotated tree-walk trace (node, contenders, outcome, action) for a ready set you choose, with the slots-saved count from pruning.
- A one-page runbook mapping a measured `q` to a starting level and expected delay regime.
- A diagram (adapt `assets/limited-contention-protocols.svg`) for your station count.

Start with [`outputs/prompt-limited-contention-protocols.md`](../outputs/prompt-limited-contention-protocols.md).

## Exercises

1. For `k = 3, 5, 10, 50` compute `k·(1/k)·(1−1/k)^(k−1)` by hand and confirm the monotone approach to `1/e`. At what `k` are you within 1% of the asymptote?
2. On the 8-leaf tree, list the exact slot-by-slot probes when **A, D, and G** are ready (no pruning). Then redo it *with* both pruning rules and count slots saved.
3. A field of 64 sensors estimates `q = 18` ready stations from recent traffic. Compute `⌊log₂ q⌋`, state which tree level the walk starts at, and how many nodes contend in that first round.
4. Argue why starting at the root under heavy load wastes a slot, using the expected-one-contender condition `2^(−i)·q = 1`.
5. Construct a ready set on the 8-leaf tree where the guaranteed-collision skip rule fires **twice** in a single walk. Show the trace.
6. Your estimator of `q` is consistently 2× too high (overestimates load). Predict the effect on delay and efficiency, and which regime you drift toward.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Limited-contention | "A mix of ALOHA and reservation" | Stations split into groups; only one group contends per slot, so contention size `k` is bounded and tunable |
| Adaptive Tree Walk | "Binary search for stations" | Depth-first probe of a binary tree of stations; collision → recurse, idle/single → prune (Capetanakis 1979) |
| Optimal `p = 1/k` | "Each station sends 1/k of the time" | The transmit probability maximizing `k·p·(1−p)^(k−1)`; success then approaches `1/e` |
| `1/e` ceiling | "ALOHA tops out at 37%" | Asymptotic per-slot success of *symmetric* contention as `k → ∞`; why lowering `k` is the only lever |
| Starting level `i = log₂(q)` | "Start deeper when busy" | Tree level where expected contenders per node `2^(−i)·q` ≈ 1 |
| Idle-subtree stop | "Empty means skip" | An idle probe proves no ready station below; its children are never probed |
| Guaranteed-collision skip | "We already know it collides" | If parent collided and one child is idle, the sibling must collide — skip its probe |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., §4.2.4 "Limited-Contention Protocols" (the source for this lesson) and §4.2.3 collision-free protocols for contrast.
- J. Capetanakis, "Tree Algorithms for Packet Broadcast Channels," *IEEE Transactions on Information Theory*, vol. 25, no. 5, 1979 — the formal tree-walk analysis.
- R. Dorfman, "The Detection of Defective Members of Large Populations," *Annals of Mathematical Statistics*, vol. 14, 1943 — the group-testing origin.
- Bertsekas & Gallager, *Data Networks*, 2nd ed., 1992 — improved tree algorithms and the pruning optimizations.
- IEEE Std 802.3 (CSMA/CD) and the slotted-ALOHA literature for the contention baselines being improved upon.
