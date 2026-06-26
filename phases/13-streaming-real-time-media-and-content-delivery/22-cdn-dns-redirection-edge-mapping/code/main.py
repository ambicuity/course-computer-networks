"""CDN DNS redirection and edge mapping simulator.

Models a CDN with:
  * an origin server
  * a set of edge nodes, each with a network location and a load counter
  * an edge map from client IP prefixes to network regions
  * an authoritative name server that resolves www.cdn.com to the
    nearest healthy edge node for the requesting resolver's IP

Demonstrates three failure modes:
  * overloaded nearest node -> spill to the next nearest (load-aware)
  * stale edge map -> client mapped to the wrong region / far node
  * DNS cache TTL -> client pinned to a node that has since failed

Stdlib only. Run with:  python3 code/main.py
"""

import ipaddress
import random


class EdgeNode:
    def __init__(self, name, region, capacity):
        self.name = name
        self.region = region
        self.capacity = capacity
        self.load = 0
        self.alive = True

    def is_overloaded(self):
        return self.load >= self.capacity

    def __repr__(self):
        return "%s(%s)" % (self.name, self.region)


class CDNNameServer:
    """Authoritative name server run by the CDN.

    Holds an edge map (prefix -> region) and resolves a client's
    local DNS resolver IP to the nearest healthy, non-overloaded
    edge node.
    """

    def __init__(self, nodes, edge_map, load_aware=True):
        self.nodes = nodes
        self.edge_map = edge_map  # list of (network, region)
        self.load_aware = load_aware
        # Static region distance table (small world: regions close to self)
        self.distance = {
            ("sydney", "sydney"): 5,
            ("sydney", "singapore"): 40,
            ("sydney", "amsterdam"): 180,
            ("sydney", "boston"): 200,
            ("singapore", "singapore"): 5,
            ("singapore", "sydney"): 40,
            ("singapore", "amsterdam"): 120,
            ("singapore", "boston"): 160,
            ("amsterdam", "amsterdam"): 5,
            ("amsterdam", "boston"): 70,
            ("amsterdam", "singapore"): 120,
            ("amsterdam", "sydney"): 180,
            ("boston", "boston"): 5,
            ("boston", "amsterdam"): 70,
            ("boston", "singapore"): 160,
            ("boston", "sydney"): 200,
        }

    def lookup_region(self, resolver_ip):
        addr = ipaddress.ip_address(resolver_ip)
        for network, region in self.edge_map:
            if addr in ipaddress.ip_network(network):
                return region
        return "boston"  # default fallback

    def resolve(self, resolver_ip):
        region = self.lookup_region(resolver_ip)
        # Rank nodes by distance to the client's region
        ranked = sorted(
            [n for n in self.nodes if n.alive],
            key=lambda n: self.distance.get((region, n.region), 999),
        )
        if not self.load_aware:
            return ranked[0] if ranked else None, region
        # Load-aware: pick the nearest node that is not overloaded
        for node in ranked:
            if not node.is_overloaded():
                node.load += 1
                return node, region
        # All overloaded: fall back to nearest anyway
        if ranked:
            ranked[0].load += 1
            return ranked[0], region
        return None, region


def section(title):
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


def show_resolution(label, results):
    print("\n%s" % label)
    by_node = {}
    for resolver_ip, region, node in results:
        by_node.setdefault(node.name if node else "NONE", []).append(resolver_ip)
    for name in sorted(by_node):
        print("  %-16s %3d clients  region(s): %s" % (
            name, len(by_node[name]),
            ", ".join(sorted(set(r for _, r, _ in results if _ and _.name == name)))))


def main():
    random.seed(1)
    nodes = [
        EdgeNode("edge-syd", "sydney", capacity=1000),
        EdgeNode("edge-sin", "singapore", capacity=1000),
        EdgeNode("edge-ams", "amsterdam", capacity=1000),
        EdgeNode("edge-bos", "boston", capacity=1000),
    ]
    edge_map = [
        ("203.0.113.0/24", "sydney"),
        ("198.51.100.0/24", "amsterdam"),
        ("192.0.2.0/24", "boston"),
        ("203.0.114.0/24", "singapore"),
    ]

    resolvers = (
        ["203.0.113.%d" % i for i in range(1, 60)]   # sydney
        + ["198.51.100.%d" % i for i in range(1, 60)]  # amsterdam
        + ["192.0.2.%d" % i for i in range(1, 60)]     # boston
        + ["203.0.114.%d" % i for i in range(1, 60)]   # singapore
    )
    random.shuffle(resolvers)

    section("Normal redirection (load-aware, all nodes healthy)")
    ns = CDNNameServer(nodes, edge_map, load_aware=True)
    results = []
    for ip in resolvers:
        node, region = ns.resolve(ip)
        results.append((ip, region, node))
    show_resolution("clients per edge node", results)
    print("\n  Each region resolves to its local node. Origin never contacted.")

    section("Failure mode: nearest node overloaded -> spill to next nearest")
    # Reset loads; overload the sydney node
    for n in nodes:
        n.load = 0
        n.alive = True
    nodes[0].load = nodes[0].capacity  # edge-syd full
    ns2 = CDNNameServer(nodes, edge_map, load_aware=True)
    spilt_results = []
    for ip in ["203.0.113.%d" % i for i in range(1, 40)]:
        node, region = ns2.resolve(ip)
        spilt_results.append((ip, region, node))
    show_resolution("sydney clients (nearest node full)", spilt_results)
    print("  -> sydney clients spill to the next nearest healthy node")
    print("     (singapore), which is farther but not overloaded.")

    section("Failure mode: stale edge map -> wrong region")
    # One sydney prefix mistakenly mapped to boston
    stale_map = list(edge_map)
    stale_map[0] = ("203.0.113.0/24", "boston")  # should be sydney
    for n in nodes:
        n.load = 0
        n.alive = True
    ns3 = CDNNameServer(nodes, stale_map, load_aware=True)
    stale_results = []
    for ip in ["203.0.113.%d" % i for i in range(1, 30)]:
        node, region = ns3.resolve(ip)
        stale_results.append((ip, region, node))
    show_resolution("stale-map sydney clients", stale_results)
    print("  -> these clients are sent to edge-bos (far node) because the")
    print("     edge map maps their prefix to the wrong region. Detectable")
    print("     from DNS logs: a resolver in AS-Oceania returns a US node.")

    section("Failure mode: DNS cache TTL pins client to a now-dead node")
    for n in nodes:
        n.load = 0
        n.alive = True
    ns4 = CDNNameServer(nodes, edge_map, load_aware=True)
    node_first, region = ns4.resolve("203.0.113.5")
    print("\n  First resolution for 203.0.113.5 -> %s (%s)" % (node_first, region))
    # Simulate that node failing AFTER the answer is cached
    node_first.alive = False
    cached_node, _ = ns4.resolve("203.0.113.5")
    # In a real DNS-cache scenario the client would NOT re-query, so it
    # would keep using the dead node's IP until the TTL expires.
    print("  Node %s is now dead. A client with a cached DNS answer keeps" % node_first.name)
    print("  using its IP until the TTL expires, hitting a failed node.")
    # A fresh (uncached) query would be redirected:
    fresh_node, _ = ns4.resolve("203.0.113.6")
    print("  A fresh query is redirected to %s instead." % fresh_node)

    section("Summary")
    print("\n  DNS redirection : CDN name server returns the nearest edge node IP")
    print("  edge map        : client IP prefix -> network region (private table)")
    print("  load-aware spill: nearest node full -> next nearest healthy node")
    print("  stale edge map  : wrong region -> far node (detectable from DNS logs)")
    print("  DNS cache TTL   : pins a client to a node that may later fail")


if __name__ == "__main__":
    main()
