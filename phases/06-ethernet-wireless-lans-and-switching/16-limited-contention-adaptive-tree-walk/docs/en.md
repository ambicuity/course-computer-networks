# Limited-Contention Protocols and the Adaptive Tree Walk Algorithm

> A pure contention protocol (slotted ALOHA, CSMA) has unbeatable low-load delay but caps at `1/e ≈ 0.368` success probability per slot when k stations contend at optimal `p = 1/k`. A collision-free protocol (bit-map, countdown) has high efficiency under load but burns an N-bit scan at low load. **Limited-contention protocols** split the difference: divide stations into groups, let each group compete in its own slot, and tune the group size so the system operates near the *left* end of the `kp(1-p)^(k-1)` curve, where contention is light and the success probability is near 1. The **adaptive tree walk** (Capetanakis 1979) does this dynamically using a binary tree: on a collision at slot 0, descend into the left subtree; on an idle slot, the right subtree is guaranteed to be active so it is skipped; on a success, the next slot starts from the parent. Each node at level i covers a fraction `2^-i` of the stations, so the search should start at the level where the expected number of ready stations per slot is 1, i.e., `i = log2 q` for q estimated ready stations. This lesson derives the optimal p, walks the tree with eight stations, and quantifies the load-adaptive depth.

**Type:** Build
**Languages:** Python (stdlib simulator + tree walker)
**Prerequisites:** Slotted ALOHA and the 1/e ceiling, CSMA, bit-map and binary countdown from the prior lesson
**Time:** ~80 minutes

## Learning Objectives

- Derive the optimal transmission probability `p = 1/k` for a symmetric contention channel and explain the `1/e` ceiling on per-slot success.
- Sketch the `kp(1-p)^(k-1)` acquisition-probability curve and identify why limited-contention protocols move the system leftward on it.
- Walk the adaptive tree walk algorithm through a collision among stations A..H and identify which slots are tried, which are skipped, and why.
- Compute the optimal search depth `i = log2 q` for an estimated q ready stations and choose the start node for a given load.
- Implement both a fixed-group and an adaptive tree walk simulator in stdlib Python and compare slot counts at low and high load.

## The Problem

A satellite down-link broadcasts position reports from 256 industrial sensors in a mining fleet. ALOHA wastes 36% of capacity at the fleet's typical 30% channel utilisation; CSMA's carrier sense cannot work because the down-link is one-way. The team needs a contention protocol that **adapts**: at 3 a.m. when only ten trucks are reporting, it should run with low delay like pure ALOHA; at 9 a.m. when 200 trucks are queued, it should run with the efficiency of a collision-free protocol.

A fixed-collision-free protocol (bit-map) spends 256 bits per cycle finding the active set, even when only 10 are ready. Pure ALOHA at 200 ready stations collapses to `kp(1-p)^(k-1) ≈ 200 x 0.005 x 0.367 ≈ 0.37`, near the floor of the curve. The team needs a protocol that *moves the operating point* with the load: 1 active station per slot at all times, regardless of how many total stations exist.

## The Concept

The chapter pulls two ideas together: an analysis of the symmetric contention channel that shows where the curve is best, and a tree algorithm that uses that insight dynamically.

### The symmetric contention ceiling

For k stations each transmitting with probability p, the per-slot success probability is exactly one station transmitting and the rest silent:

```
Pr[success] = k * p * (1 - p)^(k - 1)
```

Differentiate with respect to p, set to zero, and `p = 1/k` is optimal. Substituting:

```
Pr[success with optimal p] = ((k - 1) / k)^(k - 1)   →   1/e   as k → ∞
```

The ceiling is real and unforgiving: with 5 contenders, the per-slot success probability is already `(4/5)^4 ≈ 0.41`; with 1000, it is `0.367...`. The only way to do better is to put **fewer stations in each slot** — which is the entire motivation for limited-contention protocols.

### The idea: fewer stations per slot, more slots

A limited-contention protocol divides the N stations into groups (not necessarily disjoint). Group g contends in slot g. If the group is small enough, the per-slot success probability is high; the protocol uses as many slots as needed to keep each group near `k = 1`. The art is choosing the group size dynamically.

Special cases from the chapter:

| Group size | Regime | Result |
|---|---|---|
| 1 | Collision-free | Bit-map, countdown. Best efficiency, terrible low-load delay. |
| 2 | Light contention | `p^2` is small, almost no collisions |
| k=N | Slotted ALOHA | Best low-load delay, worst efficiency |
| Adaptive | Tuned | The adaptive tree walk |

### The adaptive tree walk

Place the N stations at the leaves of a balanced binary tree, addressable by 0/1 paths. The algorithm:

1. Slot 0: all stations under the root may try.
2. If a slot is **idle** (0 contenders) or **successful** (1 contender), that subtree is done. Move to the next slot.
3. If a slot is a **collision** (2+ contenders), recurse into the children: slot for the left subtree, slot for the right.
4. Skip rule: if a slot is idle and the parent had a collision, the *other* subtree must contain all the remaining contenders, so its slot is tried *immediately* without another probe.

The 8-station tree from Fig. 4-10:

```
            [1]            level 0 (root)
           /   \
         [2]   [3]         level 1
        / \    / \
      [4][5] [6][7]        level 2 (leaves A..H under 4..7)
      A B   C D  E F G H
```

If only G and H are ready, the trace is:

| Slot | Subtree | Outcome | Next slot |
|---|---|---|---|
| 0 | root [1] | collision (G, H both under it) | 1 = left [2] |
| 1 | left [2] | idle (no one under 2) | skip 2 ([3] is guaranteed active) |
| 3 | right [3] | collision | 4 = [6] |
| 4 | [6] | idle | skip 5 ([7] is guaranteed active) |
| 7 | [7] | collision | 8 = leaf E? No: descend to G, H under 7 |
| 8 | G (under 7 left) | success | 9 = H (under 7 right) |
| 9 | H | success | done |

Total slots: 6 (with skips), not 9. The key insight: an idle slot *tells* the protocol the other subtree of the parent is the active one.

### Choosing the start level

If each station knows (or estimates) q, the number of ready stations, the optimal level to start the search is the one at which the expected number of contenders per slot is 1. Each node at level i covers `2^-i` of the stations, so we want `2^-i * q = 1`, giving `i = log2 q`.

- q = 1 -> start at level 0 (root), one slot
- q = 8 -> start at level 3 (leaves), pure collision-free
- q = 32, N = 1024 -> start at level 5, descend if collision

This is the load-adaptive behaviour. When load is light, the search starts at the root and behaves like slotted ALOHA. When load is heavy, the search starts deep and behaves like bit-map. The transition is continuous in q.

### Why it beats both pure ALOHA and bit-map

At low load, the tree walk takes one or two slots to find a single ready station — about the same as slotted ALOHA. At high load, it acts like bit-map, walking the full tree to enumerate ready stations. The middle ground is where it shines: with 32 of 1024 stations ready, the search starts at level 5 and the inner work is bounded by the active subtree, not the full tree. Empirical studies show the adaptive tree walk beats both ALOHA and bit-map across the full load spectrum.

## Build It

`code/main.py` implements two stdlib-only tools:

1. **Success-probability curve** — for k in [1..32], compute `k p (1-p)^(k-1)` at the optimal `p = 1/k` and show the `1/e` ceiling.
2. **Adaptive tree walk simulator** — given N, a binary-tree depth, and a set of ready stations, runs the algorithm slot by slot, prints the slot outcomes (idle/success/collision), and reports total slots used. Includes the skip rule: an idle slot at a sibling means the *other* sibling is guaranteed active.
3. **Comparator** — runs the tree walk at varying q and plots (text-mode) the slots required per frame, contrasted with the bit-map's N-slot scan.

Run `python3 code/main.py` and watch the slot count grow sub-linearly with q.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Pick the start level | q, N | You choose `i = log2(q)` and start the search at node `2^i` |
| Trace one tree walk | N, ready set | You produce a slot table with idle/success/collision outcomes and skips |
| Compare protocols | Per-frame slots | Tree walk is between ALOHA and bit-map; ALOHA best at q=1, bit-map best at q=N |
| Tune for a target latency | Slot budget | You invert the slot budget to find the deepest admissible start level |
| Verify the `1/e` ceiling | k, p | Per-slot success is `k p (1-p)^(k-1) ≤ 1/e` regardless of k |

Wireshark/observer hint: in radio protocols (802.11 DCF) the same idea shows up as the EDCA backoff: each Access Category has its own contention window, so voice and data do not contend in the same slot.

## Ship It

Produce one reusable artifact under `outputs/`:

- A **success-probability plot** (text mode) showing `k p (1-p)^(k-1)` for k=1..32 at `p = 1/k`.
- An **adaptive tree walk trace** for a chosen N and ready set, with the slot table.
- A **selection note**: when the tree walk beats ALOHA, when it loses, and how to estimate q in a real deployment (e.g., exponential moving average of contention slots per successful frame).

Start from `outputs/prompt-limited-contention-adaptive-tree-walk.md`.

## Exercises

1. Prove by differentiation that `p = 1/k` maximises `k p (1-p)^(k-1)`. Then plot the function for k=2, 4, 8 and identify the peak.
2. With 16 stations and q=4 ready, compute the optimal start level `i = log2 q` and trace the first three slots. Where would the algorithm go next on a collision at level 2?
3. Re-trace the tree walk for stations {A, C, E, G} ready out of N=8. List every slot, the outcome, and the skip rule applications.
4. Compare, on N=64, the slots-per-frame of: (a) slotted ALOHA at optimal p, (b) bit-map, (c) adaptive tree walk at q=8 and q=32. State which wins at each load.
5. Implement the simple "no-skip" variant of the tree walk (always descend both children on collision) and show the slot savings from the skip rule for stations {G, H} on N=8.
6. Why is the "q estimate" critical, and what happens if q is severely underestimated (e.g., actual q=64, estimate q=4)? Identify the failure mode and a defensive rule.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Limited-contention | "groups of stations" | Protocol that partitions stations into groups, each contending in its own slot, so per-slot k is small |
| Acquisition probability | "success in a slot" | `k p (1-p)^(k-1)`, the chance some station acquires the channel in a given slot |
| 1/e ceiling | "0.368" | Asymptotic upper bound on per-slot success probability for symmetric contention as k → ∞ |
| Optimal p | "1/k" | The transmission probability that maximises per-slot success for k contenders |
| Adaptive tree walk | "Capetanakis 1979" | Algorithm that walks a binary tree of stations depth-first, using collisions to descend and idles to skip subtrees |
| Start level | "log2 q" | The depth at which the search begins, computed from an estimate q of ready stations |
| Skip rule | "an idle proves the sibling is active" | Optimization that lets the algorithm try the sibling subtree without probing when one subtree goes idle after a collision |
| Subtree coverage | "2^-i of stations" | Each level-i node in a balanced binary tree covers a fraction 2^-i of the N stations |

## Further Reading

- **Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §4.2.4 "Limited-Contention Protocols"** — the source chapter.
- **Capetanakis, J. (1979), "Tree Algorithms for Packet Broadcast Channels," *IEEE Trans. Inf. Theory* 25(5)** — original adaptive tree walk paper.
- **Bertsekas, D. & Gallager, R. (1992), *Data Networks* (2nd ed.), §4.4** — extensions to the basic tree algorithm, including the "modified tree algorithm" (MTA) and its variants.
- **Dorfman, R. (1943), "The Detection of Defective Members of Large Populations," *Annals of Mathematical Statistics* 14(4)** — the original group-testing analogy.
- **IEEE 802.11-2020, §9.2.5 "DCF access procedure"** — the modern descendant of these ideas: contention window doubles on collision, restarts on success.
- **Rom, R. & Sidi, M. (1990), *Multiple Access Protocols: Performance and Analysis*** — the graduate-level treatment of ALOHA, tree, and splitting algorithms.
