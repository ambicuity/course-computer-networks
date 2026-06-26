#!/usr/bin/env python3
"""RFC 5424 syslog parser + causal reorder engine.

Parses syslog messages from a file (or stdin if path is '-') and prints:

  1. Per-message decoded PRI (facility / severity), timestamp normalized
     to UTC microseconds, hostname, app-name, procid, msgid, SD-elements,
     and message body.
  2. Causal reorder of all messages by synchronized timestamp -- the
     true incident-ordering, not the on-disk arrival order.

This is the offline form of what production SIEMs do at ingest: parse,
extract, normalize, sort. With NTP-synced hosts the sort gives causal
order; without sync it gives a misleading chronology.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

PRI_RE = re.compile(r"^<(\d{1,3})>1?\s+")
SD_RE = re.compile(r"\[([^\]]+)\]")
FACILITY_NAMES = {
    0: "kern", 1: "user", 2: "mail", 3: "daemon", 4: "auth",
    5: "syslog", 6: "lpr", 7: "news", 8: "uucp", 9: "cron",
    10: "authpriv", 11: "ftp",
    16: "local0", 17: "local1", 18: "local2", 19: "local3",
    20: "local4", 21: "local5", 22: "local6", 23: "local7",
}
SEVERITY_NAMES = {
    0: "emerg", 1: "alert", 2: "crit", 3: "err", 4: "warning",
    5: "notice", 6: "info", 7: "debug",
}


@dataclass(frozen=True)
class SyslogMessage:
    raw: str
    pri: int
    facility: int
    severity: int
    facility_name: str
    severity_name: str
    timestamp: datetime
    hostname: str
    appname: str
    procid: str
    msgid: str
    sd_elements: tuple[str, ...]
    message: str

    @property
    def epoch_us(self) -> int:
        return int(self.timestamp.timestamp() * 1_000_000)


@dataclass
class ParseStats:
    parsed: int = 0
    failed: int = 0
    sd_elements: int = 0
    hosts: set[str] = field(default_factory=set)


def parse_pri(value: str) -> tuple[int, int, int]:
    pri_int = int(value)
    return pri_int, pri_int >> 3, pri_int & 7


def parse_timestamp(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def parse_syslog_line(line: str) -> SyslogMessage | None:
    raw = line.rstrip("\n")
    match = PRI_RE.match(raw)
    if match is None:
        return None
    pri, facility, severity = parse_pri(match.group(1))
    rest = raw[match.end():]
    parts = rest.split(" ", 6)
    if len(parts) < 7:
        return None
    timestamp_s, hostname, appname, procid, msgid, sd_field, message = parts
    try:
        ts = parse_timestamp(timestamp_s)
    except ValueError:
        return None
    facility_name = FACILITY_NAMES.get(facility, f"facility{facility}")
    severity_name = SEVERITY_NAMES.get(severity, f"severity{severity}")
    sd_elements = tuple(SD_RE.findall(sd_field))
    return SyslogMessage(
        raw=raw,
        pri=pri,
        facility=facility,
        severity=severity,
        facility_name=facility_name,
        severity_name=severity_name,
        timestamp=ts,
        hostname=hostname,
        appname=appname,
        procid=procid,
        msgid=msgid,
        sd_elements=sd_elements,
        message=message.lstrip("- ").strip() or message,
    )


def render_message(msg: SyslogMessage) -> str:
    sd_render = " ".join(f"[{sd}]" for sd in msg.sd_elements) if msg.sd_elements else "-"
    return (
        f"  raw line: {msg.raw}\n"
        f"  pri={msg.pri}  facility={msg.facility_name}  severity={msg.severity_name}\n"
        f"  ts={msg.timestamp.isoformat()}  host={msg.hostname}  app={msg.appname} "
        f"procid={msg.procid}\n"
        f"  sd=[{sd_render}]\n"
        f"  msg={msg.message}"
    )


def main() -> None:
    print("=" * 64)
    print("RFC 5424 SYSLOG PARSER + CAUSAL REORDER")
    print("=" * 64)
    path = sys.argv[1] if len(sys.argv) > 1 else "-"
    lines: list[str] = []
    if path == "-":
        lines = [ln for ln in sys.stdin if ln.strip()]
        if not lines:
            print("[i] no stdin input; using embedded sample log\n")
            lines = EMBEDDED_SAMPLE.splitlines()
    else:
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [ln for ln in f if ln.strip()]
        except FileNotFoundError:
            print(f"[!] no file at {path}; falling back to embedded sample log")
            lines = EMBEDDED_SAMPLE.splitlines()

    stats = ParseStats()
    messages: list[SyslogMessage] = []
    for ln in lines:
        msg = parse_syslog_line(ln)
        if msg is None:
            stats.failed += 1
            continue
        stats.parsed += 1
        stats.hosts.add(msg.hostname)
        stats.sd_elements += len(msg.sd_elements)
        messages.append(msg)

    if not messages:
        print("[!] no valid RFC 5424 messages parsed")
        return

    print(f"Parsed {stats.parsed} messages (failed={stats.failed}, "
          f"hosts={sorted(stats.hosts)}, sd_elements={stats.sd_elements})")
    print()
    for msg in messages[:5]:
        print(render_message(msg))
        print()

    print("=" * 64)
    print("CAUSAL ORDER (sorted by synchronized timestamp)")
    print("=" * 64)
    for msg in sorted(messages, key=lambda m: m.epoch_us):
        print(
            f"  {msg.timestamp.isoformat()} {msg.hostname:<10} "
            f"{msg.appname:<6} {msg.message}"
        )


EMBEDDED_SAMPLE = (
    "<165>1 2024-03-14T03:42:01.815Z router1 ospfd 1234 - - Neighbor 10.60.0.10 dead\n"
    "<165>1 2024-03-14T03:42:01.612Z router2 bgpd 1915 - - BGP holdtimer expired\n"
    "<165>1 2024-03-14T03:42:02.001Z client sshd 2233 - - DNS lookup failed\n"
)


if __name__ == "__main__":
    main()