"""Chord DHT finger tables and successor ring simulator.

Builds an identifier ring of m bits, places actual nodes on it,
constructs the finger table for each node, and performs lookups
using both the linear successor-walk and the O(log n) finger-table
path, printing hop counts for comparison.

Stdlib only. Run with:  python3 code/main.py
"""

import hashlib


def sha1_int(s, m):
    """Map a string to an m-bit identifier using SHA-1."""
    h = hashlib.sha1(s.encode()).hexdigest()
    return int(h, 16) % (1 << m)


class ChordRing:
    def __init__(self, node_names, m=6):
        self.m = m
        self.size = 1 << m
        # Map each node name to an identifier and sort
        self.nodes = sorted(
            (sha1_int(name, m) for name in node_names)
        )
        # Deduplicate (collisions are rare for small sets)
        self.nodes = sorted(set(self.nodes))

    def successor(self, k):
        """First actual node at or after identifier k (clockwise)."""
        k = k % self.size
        for nid in self.nodes:
            if nid >= k:
                return nid
        return self.nodes[0]  # wrap around

    def predecessor_index(self, key, node_id):
        """In the finger table of node_id, return the start value that is
        the closest predecessor of key (largest start <= key, wrapping)."""
        starts = [(node_id + (1 << i)) % self.size for i in range(self.m)]
        # Filter to starts that are in (node_id, key) going clockwise
        candidates = []
        for s in starts:
            if self._in_open_interval(s, node_id, key):
                candidates.append(s)
        if not candidates:
            return None
        return max(candidates, key=lambda s: self._clockwise_distance(node_id, s, self.size))

    @staticmethod
    def _in_open_interval(x, low, high):
        """True if x is in (low, high) clockwise on the ring, not inclusive."""
        if low < high:
            return low < x < high
        # wraps around 0
        return x > low or x < high

    @staticmethod
    def _clockwise_distance(from_id, to_id, ring_size):
        return (to_id - from_id) % ring_size

    def finger_table(self, node_id):
        """Return the full finger table for node_id as list of (i, start, succ)."""
        table = []
        for i in range(self.m):
            start = (node_id + (1 << i)) % self.size
            succ = self.successor(start)
            table.append((i, start, succ))
        return table

    def lookup_linear(self, start_node, key):
        """Walk the successor chain until successor(key) is reached.
        Returns (answer_node, hops)."""
        hops = 0
        current = start_node
        answer = self.successor(key)
        # Walk clockwise until we reach the node responsible for key
        while current != answer:
            # Move to the next node clockwise
            idx = self.nodes.index(current)
            current = self.nodes[(idx + 1) % len(self.nodes)]
            hops += 1
            if hops > len(self.nodes):  # safety
                break
        return current, hops

    def lookup_finger(self, start_node, key):
        """Use finger tables to route to successor(key).
        Returns (answer_node, hops, path)."""
        answer = self.successor(key)
        current = start_node
        hops = 0
        path = [current]
        max_hops = 2 * self.m + 1
        while current != answer:
            # If key is in (current, successor(current)] then done
            succ_current = self.nodes[
                (self.nodes.index(current) + 1) % len(self.nodes)]
            if self._in_open_interval(key, current, succ_current) or key == succ_current:
                current = succ_current
                hops += 1
                path.append(current)
                break
            # Otherwise, use the closest preceding finger
            pred_start = self.predecessor_index(key, current)
            if pred_start is None:
                # No finger helps; walk to immediate successor
                current = succ_current
            else:
                next_node = self.successor(pred_start)
                if next_node == current:
                    current = succ_current
                else:
                    current = next_node
            hops += 1
            path.append(current)
            if hops > max_hops:
                break
        return current, hops, path


def section(title):
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


def main():
    # Use a small ring (m=6 -> 64 identifiers) so finger tables are readable.
    m = 6
    ring = ChordRing(
        ["node-alpha", "node-bravo", "node-charlie", "node-delta",
         "node-echo", "node-foxtrot", "node-golf", "node-hotel"],
        m=m,
    )

    section("Chord ring (m=%d, size=%d)" % (m, 1 << m))
    print("\n  Actual nodes on the ring (sorted):")
    print("   ", ring.nodes)

    section("Finger tables")
    for nid in ring.nodes:
        ft = ring.finger_table(nid)
        print("\n  Node %d finger table:" % nid)
        for i, start, succ in ft:
            print("    i=%d  start=%3d  successor(start)=%3d" % (i, start, succ))

    section("Lookup comparison")
    # Pick a few test keys and compare linear vs finger hops
    test_keys = [3, 16, 22, 40, 55, 0, 63]
    print("\n  %-6s %-10s %-18s %-18s %-20s" % (
        "key", "start", "linear hops", "finger hops", "finger path"))
    total_linear = 0
    total_finger = 0
    n = 0
    for key in test_keys:
        start = ring.nodes[0]
        ans_lin, hops_lin = ring.lookup_linear(start, key)
        ans_fin, hops_fin, path = ring.lookup_finger(start, key)
        total_linear += hops_lin
        total_finger += hops_fin
        n += 1
        print("  %-6d %-10d %-18d %-18d %s" % (
            key, start, hops_lin, hops_fin, " -> ".join(str(p) for p in path)))

    section("Scaling check")
    import math
    print("\n  nodes n = %d" % len(ring.nodes))
    print("  linear average hops expected ~ n/2 = %.1f" % (len(ring.nodes) / 2))
    print("  finger average hops expected ~ log2(n) = %.1f" % math.log2(len(ring.nodes)))
    print("  observed: linear avg = %.2f, finger avg = %.2f" % (
        total_linear / n, total_finger / n))

    section("Failure mode: node leaves, lookup via live successor still works")
    # Remove the second node and re-test one lookup
    removed = ring.nodes[1]
    ring.nodes = [x for x in ring.nodes if x != removed]
    print("\n  Removed node %d. Remaining nodes: %s" % (removed, ring.nodes))
    key = (removed + 1) % ring.size
    ans_fin, hops_fin, path = ring.lookup_finger(ring.nodes[0], key)
    print("  Lookup key=%d via finger path: %s (hops=%d)" % (
        key, " -> ".join(str(p) for p in path), hops_fin))
    print("  -> lookup still resolves to %s, the live successor." % ans_fin)

    section("Summary")
    print("\n  successor(k)    : first actual node at or after k (clockwise)")
    print("  finger table   : m entries, entry i -> successor(k + 2^i)")
    print("  linear lookup  : O(n) -- walk the successor chain")
    print("  finger lookup  : O(log n) -- each hop halves remaining distance")
    print("  robustness     : ring stays usable while live nodes remain,")


if __name__ == "__main__":
    main()
