"""Server farm load balancing simulator.

Models a front end that distributes incoming requests across a pool of
identical backend servers using one of four policies:

  * round-robin       - servers used one after the other in turn
  * ip-hash           - last N bits of the source IP select a server
  * least-connections  - server with the fewest open connections wins
  * cookie-affinity   - a session cookie pins a user to one server

Also demonstrates health-aware draining when a server fails, and the
"NAT collapse" failure mode for IP-hash.

Stdlib only. Run with:  python3 code/main.py
"""

import hashlib
import random


class Server:
    def __init__(self, name):
        self.name = name
        self.alive = True
        self.connections = 0
        self.requests = 0

    def __repr__(self):
        return self.name


class Request:
    """A single incoming request with a source IP and optional cookie."""

    def __init__(self, src_ip, cookie=None):
        self.src_ip = src_ip
        self.cookie = cookie


class LoadBalancer:
    """Front end that maps requests to servers using a chosen policy."""

    def __init__(self, servers, policy="round-robin", health_aware=True):
        self.servers = servers
        self.policy = policy
        self.health_aware = health_aware
        self._rr_index = 0
        self._affinity = {}  # cookie -> server

    def _alive(self):
        if self.health_aware:
            return [s for s in self.servers if s.alive]
        return list(self.servers)

    def _round_robin(self):
        pool = self._alive()
        if not pool:
            return None
        server = pool[self._rr_index % len(pool)]
        self._rr_index += 1
        return server

    def _ip_hash(self, req):
        pool = self._alive()
        if not pool:
            return None
        digest = hashlib.md5(req.src_ip.encode()).hexdigest()
        val = int(digest, 16)
        return pool[val % len(pool)]

    def _least_connections(self):
        pool = self._alive()
        if not pool:
            return None
        return min(pool, key=lambda s: s.connections)

    def _cookie_affinity(self, req):
        pool = self._alive()
        if not pool:
            return None
        if req.cookie and req.cookie in self._affinity:
            pinned = self._affinity[req.cookie]
            if pinned.alive or not self.health_aware:
                return pinned
        server = self._least_connections()
        if req.cookie:
            self._affinity[req.cookie] = server
        return server

    def choose(self, req):
        if self.policy == "round-robin":
            return self._round_robin()
        if self.policy == "ip-hash":
            return self._ip_hash(req)
        if self.policy == "least-connections":
            return self._least_connections()
        if self.policy == "cookie-affinity":
            return self._cookie_affinity(req)
        raise ValueError("unknown policy: %s" % self.policy)

    def handle(self, req):
        server = self.choose(req)
        if server is None:
            return None
        server.connections += 1
        server.requests += 1
        # Simulate request completion (connection closes)
        server.connections -= 1
        return server


def make_requests(n, users=50, cookie_chance=0.6):
    """Generate n requests from `users` distinct source IPs with cookies."""
    reqs = []
    for i in range(n):
        ip = "10.0.%d.%d" % (i % users, (i * 7) % 250)
        cookie = "session-%d" % (i % users) if random.random() < cookie_chance else None
        reqs.append(Request(ip, cookie))
    return reqs


def run_policy(servers, policy, reqs, health_aware=True, kill=None):
    """Run `reqs` through a fresh LB and return per-server request counts."""
    lb = LoadBalancer(list(servers), policy=policy, health_aware=health_aware)
    if kill:
        for s in servers:
            if s.name in kill:
                s.alive = False
    for r in reqs:
        lb.handle(r)
    return {s.name: s.requests for s in servers}


def section(title):
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


def show_distribution(label, counts):
    total = sum(counts.values()) or 1
    print("\n%s" % label)
    for name in sorted(counts):
        c = counts[name]
        bar = "#" * int((c / total) * 50)
        print("  %-10s %4d  %s" % (name, c, bar))


def main():
    random.seed(42)
    names = ["srv-A", "srv-B", "srv-C", "srv-D", "srv-E", "srv-F"]
    reqs = make_requests(3000, users=60)

    section("Policy comparison (6 servers, 3000 requests, all alive)")
    for policy in ["round-robin", "ip-hash", "least-connections", "cookie-affinity"]:
        servers = [Server(n) for n in names]
        counts = run_policy(servers, policy, reqs)
        show_distribution(policy, counts)

    section("Failure mode: dead server NOT drained (health_aware=False)")
    servers = [Server(n) for n in names]
    counts = run_policy(servers, "least-connections", reqs,
                        health_aware=False, kill=["srv-C"])
    show_distribution("least-connections (no health check, srv-C dead)", counts)
    print("  -> requests still sent to srv-C are lost; clients see timeouts.")

    section("Failure mode: dead server drained (health_aware=True)")
    servers = [Server(n) for n in names]
    counts = run_policy(servers, "least-connections", reqs,
                        health_aware=True, kill=["srv-C"])
    show_distribution("least-connections (health check on, srv-C drained)", counts)
    print("  -> srv-C receives 0 requests; its share is redistributed.")

    section("Failure mode: NAT collapse of IP-hash")
    nat_reqs = [Request("203.0.113.7", cookie=None) for _ in range(3000)]
    servers = [Server(n) for n in names]
    counts = run_policy(servers, "ip-hash", nat_reqs)
    show_distribution("ip-hash (all requests from one NAT IP)", counts)
    print("  -> one source IP hashes to ONE server; the farm is unbalanced.")

    section("Cookie affinity: returning user stays pinned")
    servers = [Server(n) for n in names]
    lb = LoadBalancer(servers, policy="cookie-affinity", health_aware=True)
    user_reqs = [
        Request("10.0.0.1", cookie="session-42"),
        Request("10.0.0.1", cookie="session-42"),
        Request("10.0.0.1", cookie="session-42"),
        Request("10.0.0.1", cookie="session-42"),
        Request("10.0.0.1", cookie="session-42"),
    ]
    targets = [lb.handle(r).name for r in user_reqs]
    print("\n  5 requests from the same cookie ('session-42'):")
    print("  -> all handled by:", targets)
    print("  -> affinity holds: cached session state on that server is reused.")

    section("Summary")
    print("\n  round-robin      : even but ignores real load and sessions")
    print("  ip-hash          : stable per source, collapses under NAT, no state")
    print("  least-connections: adapts to slow servers, requires per-server state")
    print("  cookie-affinity  : pins a user to a server, fragile if layers change")
    print("  health_aware=True: drains failed servers; makes a farm more reliable")
    print("                     than a single machine.")


if __name__ == "__main__":
    main()
