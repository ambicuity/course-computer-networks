#!/usr/bin/env python3
"""DNS resource record parser and name-server hierarchy simulator.

Stdlib only, no network calls. Demonstrates three things:

1. Parsing DNS zone files: each resource record is a five-tuple
   (Domain name, TTL, Class, Type, Value) per RFC 1035 section 7.1.2.
   Supported types: A, AAAA, CNAME, MX, TXT, SOA, NS, PTR.
2. A Zone class that indexes records by name and answers queries
   by type, returning authoritative RR sets.
3. A hierarchical name-server resolution simulator that mirrors the
   root -> TLD -> authoritative chain from the textbook's 10-step
   example (client -> local resolver -> root -> edu -> washington.edu
   -> cs.washington.edu). Caching by TTL is included so repeated
   lookups are shorter, just like real resolvers.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Part 1: the resource record model
# ---------------------------------------------------------------------------

VALID_TYPES: set[str] = {
    "A", "AAAA", "CNAME", "MX", "TXT", "SOA", "NS", "PTR",
}


@dataclass(frozen=True)
class ResourceRecord:
    name: str
    ttl: int
    rr_class: str
    rtype: str
    rdata: str

    def format(self) -> str:
        return f"{self.name:<24} {self.ttl:<6} {self.rr_class:<3} {self.rtype:<6} {self.rdata}"


def parse_rr_line(line: str, last_name: Optional[str] = None) -> ResourceRecord:
    """Parse one zone-file line into a ResourceRecord.

    Blank lines and comments (starting with ';') return a sentinel.
    A bare leading whitespace means 'inherit the previous owner name'.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith(";"):
        raise ValueError("blank or comment")

    inherit = line[0].isspace()
    tokens = stripped.split()
    if inherit and last_name is not None:
        owner = last_name
    else:
        owner = tokens.pop(0)
    if not tokens:
        raise ValueError("no fields after owner")

    ttl = 0
    rr_class = "IN"
    if tokens and tokens[0].isdigit():
        ttl = int(tokens.pop(0))
    if tokens and tokens[0].upper() in {"IN", "CH", "HS"}:
        rr_class = tokens.pop(0).upper()
    rtype = tokens.pop(0).upper()
    if rtype not in VALID_TYPES:
        raise ValueError(f"unknown type {rtype}")
    rdata = " ".join(tokens)
    return ResourceRecord(owner.rstrip("."), ttl, rr_class, rtype, rdata)


def parse_zone(text: str) -> list[ResourceRecord]:
    """Parse a multi-line zone file string into a list of RRs."""
    records: list[ResourceRecord] = []
    last_name: Optional[str] = None
    for raw in text.splitlines():
        try:
            rr = parse_rr_line(raw, last_name)
        except ValueError:
            continue
        last_name = rr.name
        records.append(rr)
    return records


# ---------------------------------------------------------------------------
# Part 2: a Zone with query support
# ---------------------------------------------------------------------------

@dataclass
class Zone:
    name: str
    records: list[ResourceRecord] = field(default_factory=list)

    def index(self) -> dict[str, dict[str, list[ResourceRecord]]]:
        idx: dict[str, dict[str, list[ResourceRecord]]] = {}
        for rr in self.records:
            by_type = idx.setdefault(rr.name.lower(), {})
            by_type.setdefault(rr.rtype, []).append(rr)
        return idx

    def query(self, qname: str, qtype: str = "A") -> list[ResourceRecord]:
        """Return RRs matching qname (case-insensitive) and qtype."""
        return self.index().get(qname.lower(), {}).get(qtype.upper(), [])

    def nameservers(self) -> list[str]:
        return [rr.rdata for rr in self.query(self.name, "NS")]

    def mx_records(self) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for rr in self.query(self.name, "MX"):
            parts = rr.rdata.split()
            if len(parts) == 2:
                out.append((int(parts[0]), parts[1]))
        return sorted(out)


# ---------------------------------------------------------------------------
# Part 3: hierarchical name-server resolution with TTL caching
# ---------------------------------------------------------------------------

@dataclass
class CacheEntry:
    answer: list[ResourceRecord]
    ttl_remaining: int


@dataclass
class NameServer:
    label: str
    zone_name: str
    zone: Zone

    def answer(self, qname: str, qtype: str) -> tuple[list[ResourceRecord], list[ResourceRecord], list[ResourceRecord]]:
        """Return (answers, referrals, authorities) for a query.

        If this server is authoritative for a suffix of qname it returns
        whatever records it has. If it only knows a delegation it returns
        that as a referral (NS records pointing further down).
        """
        answers = self.zone.query(qname, qtype)
        if answers:
            return answers, [], []

        parts = qname.split(".")
        for i in range(len(parts)):
            candidate = ".".join(parts[i:])
            ns_rrs = self.zone.query(candidate, "NS")
            if ns_rrs:
                return [], ns_rrs, ns_rrs
        return [], [], []


class Resolver:
    """A caching recursive resolver that walks the hierarchy."""

    def __init__(self, local: NameServer, root: NameServer, servers: list[NameServer]) -> None:
        self.local = local
        self.root = root
        self.servers = {s.label: s for s in servers}
        self.cache: dict[str, CacheEntry] = {}

    def resolve(self, qname: str, qtype: str = "A") -> list[ResourceRecord]:
        qname = qname.rstrip(".")
        cache_key = f"{qname.lower()}/{qtype.upper()}"
        if cache_key in self.cache and self.cache[cache_key].ttl_remaining > 0:
            print(f"  [cache hit] {cache_key} TTL={self.cache[cache_key].ttl_remaining}")
            return self.cache[cache_key].answer

        print(f"  Step 1: client -> local resolver  query {qname} {qtype}")
        answers, referrals, _ = self.local.answer(qname, qtype)
        if answers:
            self._cache(cache_key, answers)
            return answers

        print(f"  Step 2: local resolver -> root ({self.root.label})")
        current_server = self.root
        step = 2
        while True:
            step += 1
            answers, referrals, _ = current_server.answer(qname, qtype)
            if answers:
                print(f"  Step {step}: {current_server.label} -> ANSWER")
                self._cache(cache_key, answers)
                return answers
            if referrals:
                ns_host = referrals[0].rdata.split()[-1].rstrip(".")
                nxt = self._find_server(ns_host)
                if nxt is None:
                    print(f"  Step {step}: {current_server.label} -> referral to {ns_host} (not modelled)")
                    return []
                print(f"  Step {step}: {current_server.label} -> referral to {nxt.label}")
                current_server = nxt
            else:
                print(f"  Step {step}: {current_server.label} -> NXDOMAIN")
                return []

    def _cache(self, key: str, records: list[ResourceRecord]) -> None:
        ttl = min((r.ttl for r in records), default=0)
        self.cache[key] = CacheEntry(records, ttl)

    def _find_server(self, ns_host: str) -> Optional[NameServer]:
        ns_host = ns_host.lower()
        for s in self.servers.values():
            if s.label.lower() == ns_host:
                return s
        for qname_suffix, s in self.servers.items():
            if ns_host.endswith(qname_suffix.lower()):
                return s
        return None


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------

ROOT_ZONE_TEXT = """
; root hints
.                   518400 IN NS  a.root-servers.net
.                   518400 IN NS  b.root-servers.net
edu                 172800 IN NS  a.edu-servers.net
edu                 172800 IN NS  b.edu-servers.net
"""

EDU_ZONE_TEXT = """
edu                 172800 IN NS  a.edu-servers.net
washington.edu      172800 IN NS  ns.washington.edu
mit.edu             172800 IN NS  ns.mit.edu
"""

UW_ZONE_TEXT = """
washington.edu      86400  IN SOA ns.washington.edu admin.washington.edu 2010081501 7200 3600 1209600 3600
washington.edu      86400  IN NS  ns.washington.edu
washington.edu      86400  IN MX  10 mail.washington.edu
ns.washington.edu   86400  IN A   128.95.120.1
mail.washington.edu 86400  IN A   128.95.120.2
eng.washington.edu  86400  IN NS  ns.eng.washington.edu
cs.washington.edu   86400  IN NS  ns.cs.washington.edu
"""

CS_ZONE_TEXT = """
cs.washington.edu   86400  IN SOA ns.cs.washington.edu admin.cs.washington.edu 2010081501 7200 3600 1209600 3600
cs.washington.edu   86400  IN NS  ns.cs.washington.edu
cs.washington.edu   86400  IN MX  10 mail.cs.washington.edu
ns.cs.washington.edu  86400 IN A  128.208.3.88
mail.cs.washington.edu 86400 IN A 128.208.3.89
www.cs.washington.edu 86400 IN CNAME www-lb.cs.washington.edu
www-lb.cs.washington.edu 86400 IN A 128.208.3.90
robot.cs.washington.edu 86400 IN A 128.208.3.91
galah.cs.washington.edu  86400 IN A 128.208.3.92
flit.cs.washington.edu 86400 IN TXT "v=spf1 include:mail.cs.washington.edu -all"
"""


def main() -> None:
    print("=" * 70)
    print("DNS Resource Records -- parsing a zone file (section 7.1.2)")
    print("=" * 70)
    zone_records = parse_zone(CS_ZONE_TEXT)
    for rr in zone_records:
        print(f"  {rr.format()}")

    print()
    print("=" * 70)
    print("Querying the cs.washington.edu zone")
    print("=" * 70)
    cs_zone = Zone("cs.washington.edu", zone_records)
    for qname, qtype in [
        ("robot.cs.washington.edu", "A"),
        ("www.cs.washington.edu", "CNAME"),
        ("www-lb.cs.washington.edu", "A"),
        ("cs.washington.edu", "MX"),
        ("cs.washington.edu", "NS"),
        ("flit.cs.washington.edu", "TXT"),
        ("ns.cs.washington.edu", "A"),
    ]:
        results = cs_zone.query(qname, qtype)
        print(f"  Q {qname} {qtype} -> {len(results)} rr(s)")
        for r in results:
            print(f"      {r.format()}")

    print()
    print("=" * 70)
    print("Name-server hierarchy resolution (section 7.1.3, 10-step example)")
    print("=" * 70)

    root = NameServer("a.root-servers.net", ".", Zone(".", parse_zone(ROOT_ZONE_TEXT)))
    edu = NameServer("a.edu-servers.net", "edu", Zone("edu", parse_zone(EDU_ZONE_TEXT)))
    uw = NameServer("ns.washington.edu", "washington.edu", Zone("washington.edu", parse_zone(UW_ZONE_TEXT)))
    cs = NameServer("ns.cs.washington.edu", "cs.washington.edu", cs_zone)
    local = NameServer("ns.local.net", "local.net", Zone("local.net", []))

    resolver = Resolver(local=local, root=root, servers=[root, edu, uw, cs])

    print("\n--- First lookup: robot.cs.washington.edu (cold cache) ---")
    ans = resolver.resolve("robot.cs.washington.edu", "A")
    print(f"\n  Final answer:")
    for r in ans:
        print(f"      {r.format()}")

    print("\n--- Second lookup: galah.cs.washington.edu (warm cache) ---")
    ans2 = resolver.resolve("galah.cs.washington.edu", "A")
    print(f"\n  Final answer:")
    for r in ans2:
        print(f"      {r.format()}")

    print("\n--- Third lookup: www.cs.washington.edu (follows CNAME) ---")
    cname_ans = resolver.resolve("www.cs.washington.edu", "CNAME")
    print(f"\n  CNAME answer:")
    for r in cname_ans:
        print(f"      {r.format()}")
    a_ans = resolver.resolve("www-lb.cs.washington.edu", "A")
    print(f"  A answer:")
    for r in a_ans:
        print(f"      {r.format()}")

    print()
    print("=" * 70)
    print("Cache contents after resolution")
    print("=" * 70)
    for key, entry in resolver.cache.items():
        print(f"  {key}  TTL={entry.ttl_remaining}  records={len(entry.answer)}")


if __name__ == "__main__":
    main()