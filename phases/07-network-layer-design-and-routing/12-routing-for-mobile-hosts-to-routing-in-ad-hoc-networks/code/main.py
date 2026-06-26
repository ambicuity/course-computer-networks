"""Mobile IP handoff + AODV route discovery simulator (stdlib only).

Models:
  1. Mobile IP: home agent intercepts a packet for a roaming host, builds an
     IP-in-IP (protocol 4) tunnel to the care-of address, and the mobile host
     decapsulates. Demonstrates triangle routing.
  2. AODV (RFC 3561): on-demand route discovery via RREQ flood that records
     reverse-path state, and unicast RREP that installs forward routes.
     Includes expanding-ring search bounded by TTL and a link-failure /
     route-maintenance purge driven by missed HELLO messages.

Run:  python3 main.py   (exits 0)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Mobile IP
# ---------------------------------------------------------------------------

@dataclass
class IPHeader:
    """A minimal IPv4 header representation for the tunnel demo."""
    version: int = 4
    ihl: int = 5
    ttl: int = 64
    protocol: int = 6
    src: str = "0.0.0.0"
    dst: str = "0.0.0.0"
    payload: str = ""

    def total_length(self) -> int:
        return self.ihl * 4 + len(self.payload.encode())

    def describe(self, label: str) -> str:
        return (
            f"  [{label}] version={self.version} ihl={self.ihl} "
            f"proto={self.protocol} ttl={self.ttl} "
            f"src={self.src} dst={self.dst} "
            f"total_len={self.total_length()}"
        )


@dataclass
class BindingCache:
    home_address: str
    care_of_address: str
    home_agent: str


def mobile_ip_tunnel(
    correspondent: str,
    mobile_home: str,
    ha_address: str,
    coa: str,
    payload: str = "GET /index.html HTTP/1.1",
) -> Tuple[IPHeader, IPHeader, IPHeader]:
    """Simulate the Mobile IP data path."""
    binding = BindingCache(home_address=mobile_home,
                           care_of_address=coa, home_agent=ha_address)
    inner = IPHeader(protocol=6, ttl=64, src=correspondent,
                    dst=binding.home_address, payload=payload)
    outer = IPHeader(protocol=4, ttl=64, src=binding.home_agent,
                    dst=binding.care_of_address,
                    payload=f"<inner: {inner.total_length()}B>")
    recovered = IPHeader(protocol=inner.protocol, ttl=inner.ttl,
                         src=inner.src, dst=inner.dst, payload=inner.payload)
    return inner, outer, recovered


def print_mobile_ip_demo() -> None:
    print("=" * 70)
    print("MOBILE IP - IP-in-IP TUNNEL (RFC 5944 / RFC 2003)")
    print("=" * 70)
    inner, outer, recovered = mobile_ip_tunnel(
        correspondent="203.0.113.9",
        mobile_home="198.51.100.7",
        ha_address="198.51.100.1",
        coa="192.0.2.50",
    )
    print("Correspondent sends to mobile's home address:")
    print(inner.describe("INNER (from correspondent)"))
    print("\nHome agent intercepts + encapsulates (proto 4 = IP-in-IP):")
    print(outer.describe("OUTER (HA -> CoA)"))
    print("\nMobile host decapsulates, recovers original:")
    print(recovered.describe("RECOVERED (at mobile)"))
    print("\nTriangle routing:")
    print("  correspondent -> HA(198.51.100.1) -> CoA(192.0.2.50)")
    print("  mobile -> correspondent (direct, no HA)")
    print()


# ---------------------------------------------------------------------------
# AODV
# ---------------------------------------------------------------------------

@dataclass
class RREQ:
    source: str
    broadcast_id: int
    dest: str
    dest_seq: int
    hop_count: int = 0
    src_seq: int = 0


@dataclass
class RREP:
    dest: str
    dest_seq: int
    hop_count: int = 0
    originator: str = ""


@dataclass
class RouteEntry:
    dest: str
    next_hop: str
    hop_count: int
    dest_seq: int
    valid: bool = True


@dataclass
class AODVNode:
    name: str
    neighbors: List[str]
    routing_table: Dict[str, RouteEntry] = field(default_factory=dict)
    reverse_routes: Dict[Tuple[str, int], str] = field(default_factory=dict)
    active_neighbors: Dict[str, set] = field(default_factory=dict)
    seen_rreq: set = field(default_factory=set)
    alive: bool = True


class AODVNetwork:
    """Simulates RREQ flood + RREP reverse-path install + route purge."""

    def __init__(self, topology: Dict[str, List[str]]) -> None:
        self.nodes: Dict[str, AODVNode] = {
            n: AODVNode(name=n, neighbors=list(adj))
            for n, adj in topology.items()
        }
        self.dest_seq: Dict[str, int] = {}
        self.trace: List[str] = []

    def _log(self, msg: str) -> None:
        self.trace.append(msg)

    def route_discovery(self, src: str, dest: str,
                        dest_seq: int = 0) -> Optional[List[str]]:
        if src not in self.nodes or dest not in self.nodes:
            raise ValueError("unknown node")
        bid = 1
        rreq = RREQ(source=src, broadcast_id=bid, dest=dest,
                    dest_seq=dest_seq, hop_count=0)
        self._log(f"RREQ from {src} for {dest} (dest_seq>={dest_seq})")
        queue: deque = deque([(src, rreq)])
        self.nodes[src].seen_rreq.add((src, bid))
        found = False
        while queue:
            node_name, req = queue.popleft()
            node = self.nodes[node_name]
            if not node.alive:
                continue
            for nb_name in node.neighbors:
                nb = self.nodes[nb_name]
                if not nb.alive:
                    continue
                if (req.source, req.broadcast_id) in nb.seen_rreq:
                    continue
                nb.seen_rreq.add((req.source, req.broadcast_id))
                nb.reverse_routes[(req.source, req.broadcast_id)] = node_name
                fwd = RREQ(source=req.source, broadcast_id=req.broadcast_id,
                           dest=req.dest, dest_seq=req.dest_seq,
                           hop_count=req.hop_count + 1,
                           src_seq=req.src_seq)
                self._log(f"  {node_name} -> {nb_name}  hop={fwd.hop_count}")
                if nb_name == dest:
                    found = True
                    continue
                queue.append((nb_name, fwd))
        if not found:
            self._log("  no RREP (destination unreachable)")
            return None
        self.dest_seq[dest] = self.dest_seq.get(dest, 0) + 1
        seq = self.dest_seq[dest]
        rep = RREP(dest=dest, dest_seq=seq, hop_count=0, originator=src)
        self._log(f"RREP from {dest} (dest_seq={seq})")
        path: List[str] = [dest]
        current = dest
        while current != src:
            prev = self.nodes[current].reverse_routes.get((src, bid))
            if prev is None:
                break
            entry = RouteEntry(dest=dest, next_hop=current,
                               hop_count=rep.hop_count + 1, dest_seq=seq)
            self.nodes[prev].routing_table[dest] = entry
            self.nodes[prev].active_neighbors.setdefault(dest, set()).add(current)
            rep = RREP(dest=dest, dest_seq=seq,
                       hop_count=rep.hop_count + 1, originator=src)
            self._log(f"  {current} -> {prev}  hop={rep.hop_count} "
                      f"(install {prev}: {dest} via {current})")
            path.append(prev)
            current = prev
        path.reverse()
        return path

    def expanding_ring_search(self, src: str, dest: str,
                              max_ttl: int = 6) -> Tuple[Optional[List[str]],
                                                         int]:
        total_tx = 0
        for ttl in range(1, max_ttl + 1):
            tx = self._bounded_flood(src, dest, ttl)
            total_tx += tx
            self._log(f"  TTL={ttl}: {tx} tx (cumulative {total_tx})")
            if self._reaches(src, dest, ttl):
                return self._reconstruct(src, dest), total_tx
        return None, total_tx

    def _bounded_flood(self, src: str, dest: str, ttl: int) -> int:
        visited = {src: 0}
        queue = deque([(src, 0)])
        tx = 0
        while queue:
            node_name, depth = queue.popleft()
            if depth >= ttl:
                continue
            for nb_name in self.nodes[node_name].neighbors:
                nb = self.nodes[nb_name]
                if not nb.alive:
                    continue
                if nb_name in visited:
                    continue
                visited[nb_name] = depth + 1
                tx += 1
                if nb_name == dest:
                    return tx
                queue.append((nb_name, depth + 1))
        return tx

    def _reaches(self, src: str, dest: str, ttl: int) -> bool:
        visited = {src: 0}
        queue = deque([(src, 0)])
        while queue:
            n, d = queue.popleft()
            if d >= ttl:
                continue
            for nb in self.nodes[n].neighbors:
                if nb in visited:
                    continue
                visited[nb] = d + 1
                if nb == dest:
                    return True
                queue.append((nb, d + 1))
        return False

    def _reconstruct(self, src: str, dest: str) -> List[str]:
        prev: Dict[str, Optional[str]] = {src: None}
        queue = deque([src])
        while queue:
            n = queue.popleft()
            if n == dest:
                break
            for nb in self.nodes[n].neighbors:
                if nb not in prev:
                    prev[nb] = n
                    queue.append(nb)
        path: List[str] = []
        cur: Optional[str] = dest
        while cur is not None:
            path.append(cur)
            cur = prev.get(cur)
        path.reverse()
        return path

    def link_down(self, a: str, b: str) -> None:
        self.nodes[a].neighbors = [n for n in self.nodes[a].neighbors
                                   if n != b]
        self.nodes[b].neighbors = [n for n in self.nodes[b].neighbors
                                   if n != a]
        self._log(f"LINK DOWN: {a} <-> {b} (missed HELLO)")

    def purge_route(self, gone: str) -> List[str]:
        purged: List[str] = []
        for node in self.nodes.values():
            for dest, entry in list(node.routing_table.items()):
                if entry.next_hop == gone:
                    entry.valid = False
                    purged.append(f"{node.name}:{dest} via {gone} -> INVALID")
                    actives = node.active_neighbors.get(dest, set())
                    for an in actives:
                        if dest in self.nodes[an].routing_table:
                            self.nodes[an].routing_table[dest].valid = False
                            purged.append(f"  notify {an}: {dest} via "
                                          f"{node.name} -> INVALID")
        return purged

    def print_routing_tables(self) -> None:
        print("\nPer-node routing tables (AODV):")
        for name in sorted(self.nodes):
            node = self.nodes[name]
            print(f"  {name}: ", end="")
            if not node.routing_table:
                print("(empty)")
                continue
            entries = []
            for d, e in node.routing_table.items():
                flag = "OK" if e.valid else "BAD"
                entries.append(f"{d}->next:{e.next_hop},"
                               f"h={e.hop_count},seq={e.dest_seq},{flag}")
            print("  ".join(entries))


TEXTBOOK_TOPOLOGY: Dict[str, List[str]] = {
    "A": ["B", "D"],
    "B": ["A", "C", "D"],
    "C": ["B", "E"],
    "D": ["A", "B", "F", "G"],
    "E": ["C", "G", "H"],
    "F": ["D", "G"],
    "G": ["D", "E", "F", "H", "I"],
    "H": ["E", "G", "I"],
    "I": ["G", "H"],
}


def main() -> int:
    print_mobile_ip_demo()

    print("=" * 70)
    print("AODV ROUTE DISCOVERY (RFC 3561) - topology Fig. 5-20")
    print("=" * 70)
    net = AODVNetwork(TEXTBOOK_TOPOLOGY)
    path = net.route_discovery("A", "I", dest_seq=0)
    print("\nTrace:")
    for line in net.trace:
        print(line)
    print(f"\nDiscovered path A->I: {' -> '.join(path) if path else 'NONE'}")
    net.print_routing_tables()

    print("\n" + "=" * 70)
    print("EXPANDING-RING SEARCH (TTL 1,2,3,...)")
    print("=" * 70)
    net2 = AODVNetwork(TEXTBOOK_TOPOLOGY)
    net2.trace.clear()
    found_path, cost = net2.expanding_ring_search("A", "I", max_ttl=4)
    for line in net2.trace:
        print(line)
    print(f"\nPath: {' -> '.join(found_path) if found_path else 'NONE'}")
    print(f"Total broadcasts with expanding ring: {cost}")
    full_flood = sum(len(n.neighbors) for n in net2.nodes.values()) // 2 + 1
    print(f"Full network flood would cost ~{full_flood} transmissions")

    print("\n" + "=" * 70)
    print("ROUTE MAINTENANCE - node G switched off (missed HELLO)")
    print("=" * 70)
    net.nodes["G"].alive = False
    net.link_down("D", "G")
    net.link_down("H", "G")
    net.link_down("F", "G")
    net.link_down("E", "G")
    net.link_down("I", "G")
    purged = net.purge_route("G")
    for p in purged:
        print(p)
    net.print_routing_tables()

    print("\nRediscovering A->I after G failure:")
    net3 = AODVNetwork(TEXTBOOK_TOPOLOGY)
    net3.nodes["G"].alive = False
    net3.link_down("D", "G")
    net3.link_down("H", "G")
    net3.link_down("F", "G")
    net3.link_down("E", "G")
    net3.link_down("I", "G")
    new_path = net3.route_discovery("A", "I", dest_seq=1)
    print(f"New path A->I: {' -> '.join(new_path) if new_path else 'NONE'}")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
