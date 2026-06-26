#!/usr/bin/env python3
"""Zone file parser and zone-transfer simulator (RFC 1035, RFC 1995, RFC 5936).

Loads a small BIND-style zone file, prints the parsed SOA timers, NS set, and
record counts, then simulates an AXFR stream and an IXFR diff between two
versions of the same zone. No network calls; runs anywhere with `python3`.

Run with `python3 main.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Soa:
    mname: str
    rname: str
    serial: int
    refresh: int
    retry: int
    expire: int
    minimum: int


@dataclass
class Zone:
    origin: str
    ttl: int
    soa: Soa
    records: List[Tuple[str, str, str, str, int]] = field(default_factory=list)

    def ns_set(self) -> List[str]:
        return sorted({rdata for name, rtype, _, rdata, _ in self.records if rtype == "NS"})


ZONE_TEXT = """$ORIGIN example.com.
$TTL 86400
@  IN  SOA  ns1.example.com. admin.example.com. (
        2026062501  3600  1800  1209600  300 )
        IN  NS   ns1.example.com.
        IN  NS   ns2.example.com.
        IN  MX   10 mail.example.com.
ns1     IN  A    192.0.2.10
ns2     IN  A    192.0.2.11
mail    IN  A    192.0.2.20
www     IN  A    192.0.2.30
ftp     IN  CNAME www.example.com.
"""

ZONE_TEXT_V2 = """$ORIGIN example.com.
$TTL 86400
@  IN  SOA  ns1.example.com. admin.example.com. (
        2026062502  3600  1800  1209600  300 )
        IN  NS   ns1.example.com.
        IN  NS   ns2.example.com.
        IN  MX   10 mail.example.com.
ns1     IN  A    192.0.2.10
ns2     IN  A    192.0.2.11
mail    IN  A    192.0.2.20
www     IN  A    192.0.2.30
ftp     IN  CNAME www.example.com.
api     IN  A    192.0.2.40
"""


def _tokenize(line: str) -> List[str]:
    line = line.split(";")[0]
    line = line.replace("(", " ").replace(")", " ").replace("\t", " ")
    return [tok for tok in line.split() if tok]


def parse_zone(text: str) -> Zone:
    origin = "."
    default_ttl = 86400
    soa: Optional[Soa] = None
    records: List[Tuple[str, str, str, str, int]] = []
    last_name: Optional[str] = None
    paren: List[str] = []
    in_paren = False
    soa_remaining: List[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("$ORIGIN"):
            origin = line.split()[1]
            if not origin.endswith("."):
                origin += "."
            continue
        if line.startswith("$TTL"):
            default_ttl = int(line.split()[1])
            continue
        tokens = _tokenize(line)
        if in_paren:
            paren.extend(tokens)
            if ")" in raw_line:
                in_paren = False
                soa_remaining = paren
                paren = []
                if soa is None and len(soa_remaining) >= 7:
                    mname, rname = soa_remaining[0], soa_remaining[1]
                    serial = int(soa_remaining[2])
                    refresh = int(soa_remaining[3])
                    retry = int(soa_remaining[4])
                    expire = int(soa_remaining[5])
                    minimum = int(soa_remaining[6])
                    soa = Soa(mname, rname, serial, refresh, retry, expire, minimum)
                continue
        if "(" in raw_line and ")" not in raw_line:
            in_paren = True
            paren = []
            head = raw_line.split("(", 1)[0]
            tokens = _tokenize(head)
            name = tokens[0] if tokens and tokens[0] != "@" else "@"
            if tokens and tokens[0] == "@":
                name = origin
            elif tokens and not tokens[0].endswith("."):
                name = f"{tokens[0]}.{origin}"
            else:
                name = tokens[0]
            last_name = name
            continue
        if not tokens:
            continue
        idx = 0
        name = last_name
        if re.match(r"^[A-Za-z0-9_*-]", tokens[0]) and tokens[0] not in ("IN", "CH", "ANY"):
            if tokens[0] == "@":
                name = origin
            elif tokens[0].endswith("."):
                name = tokens[0]
            else:
                name = f"{tokens[0]}.{origin}"
            idx = 1
            last_name = name
        if name is None:
            continue
        rclass = "IN"
        if tokens[idx] == "IN":
            idx += 1
        rtype = tokens[idx]
        idx += 1
        ttl = default_ttl
        if idx < len(tokens) and tokens[idx].isdigit():
            ttl = int(tokens[idx])
            idx += 1
        rdata = " ".join(tokens[idx:])
        records.append((name, rtype, rclass, rdata, ttl))

    if soa is None:
        raise ValueError("zone has no SOA record")
    return Zone(origin=origin, ttl=default_ttl, soa=soa, records=records)


def refresh_schedule(soa: Soa) -> Dict[str, int]:
    return {
        "next_refresh_in_s": soa.refresh,
        "retry_interval_s": soa.retry,
        "expire_after_s": soa.expire,
        "negative_cache_ttl_s": soa.minimum,
    }


def axfr_stream(zone: Zone) -> List[Tuple[str, str, str, str, int]]:
    """RFC 5936: SOA, every record, then SOA again to mark end of transfer."""
    out: List[Tuple[str, str, str, str, int]] = []
    out.append((zone.origin, "SOA", "IN", _soa_text(zone.soa), zone.ttl))
    out.extend(zone.records)
    out.append((zone.origin, "SOA", "IN", _soa_text(zone.soa), zone.ttl))
    return out


def _soa_text(soa: Soa) -> str:
    return (
        f"{soa.mname} {soa.rname} {soa.serial} {soa.refresh} {soa.retry} "
        f"{soa.expire} {soa.minimum}"
    )


def ixfr_diff(old: Zone, new: Zone) -> Dict[str, List[Tuple[str, str, str, str, int]]]:
    """Return {'deleted': [...], 'added': [...]} between two zone versions."""
    old_set = {(n, t, c, d, ttl) for n, t, c, d, ttl in old.records}
    new_set = {(n, t, c, d, ttl) for n, t, c, d, ttl in new.records}
    return {
        "deleted": sorted(old_set - new_set),
        "added": sorted(new_set - old_set),
        "old_serial": old.soa.serial,
        "new_serial": new.soa.serial,
    }


def main() -> None:
    print("=" * 64)
    print("ZONE PARSER + AXFR / IXFR SIMULATOR  --  RFC 1035 / RFC 5936 / RFC 1995")
    print("=" * 64)

    z = parse_zone(ZONE_TEXT)
    print(f"\nLoaded zone: origin={z.origin}  default TTL={z.ttl}")
    print(f"SOA: mname={z.soa.mname}  rname={z.soa.rname}")
    print(f"     serial={z.soa.serial}  refresh={z.soa.refresh}  retry={z.soa.retry}  "
          f"expire={z.soa.expire}  minimum={z.soa.minimum}")
    print(f"NS set ({len(z.ns_set())}):")
    for ns in z.ns_set():
        print(f"  {ns}")
    print(f"record count: {len(z.records)}")

    print("\nRefresh schedule derived from SOA timers:")
    for k, v in refresh_schedule(z.soa).items():
        print(f"  {k}: {v}")

    print("\nAXFR (RFC 5936) stream:")
    stream = axfr_stream(z)
    print(f"  messages: {len(stream)}  (first and last are SOA bookends)")
    print(f"  first: {stream[0][:4]}")
    print(f"  last : {stream[-1][:4]}")

    z2 = parse_zone(ZONE_TEXT_V2)
    print(f"\nIXFR (RFC 1995) between serial {z.soa.serial} and {z2.soa.serial}:")
    diff = ixfr_diff(z, z2)
    print(f"  deleted {len(diff['deleted'])} record(s):")
    for r in diff["deleted"]:
        print(f"    - {r[0]:30s} {r[1]:6s} {r[3]}")
    print(f"  added   {len(diff['added'])} record(s):")
    for r in diff["added"]:
        print(f"    + {r[0]:30s} {r[1]:6s} {r[3]}")

    print("\nOperational reminders:")
    print("  - Increment serial on every edit; never roll back to a smaller value (RFC 1982).")
    print("  - Send NOTIFY (RFC 1996) to all NS hosts on reload.")
    print("  - Restrict AXFR with allow-transfer ACLs.")
    print(f"  - Secondary drops the zone after EXPIRE = {z.soa.expire} s "
          f"(~{z.soa.expire // 86400} days) without a successful refresh.")


if __name__ == "__main__":
    main()
