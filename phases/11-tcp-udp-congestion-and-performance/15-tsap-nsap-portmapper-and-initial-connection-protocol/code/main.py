#!/usr/bin/env python3
"""Offline portmapper and inetd simulator for Tanenbaum Ch. 6 (section 6.2.1).

The portmapper is a well-known service on TSAP 111 that answers
PMAPPROC_GETPORT queries from clients and accepts PMAPPROC_SET registrations
from servers. This implementation uses a simplified JSON-over-stdin/stdout
protocol so it is easy to read; the real wire format is XDR (RFC 4506) per
RFC 1833.

The initial connection protocol (Tanenbaum Figure 6-9) is simulated by
inetd_simulator(), which polls a set of registered TSAPs and "forks" the
appropriate service the first time a connection arrives.

No network calls, no third-party packages -- pure stdlib. Run with
``python3 main.py``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field


WELL_KNOWN_TSAP_PORTMAP = 111
WELL_KNOWN_TSAP_INETD = 0  # 0 here means "many TSAPs"


@dataclass(frozen=True)
class ServiceKey:
    program: str
    version: int
    protocol: str  # "tcp" or "udp"

    def rpc_id(self) -> tuple[int, int, int]:
        proto = 6 if self.protocol == "tcp" else 17
        return (hash(self.program) & 0x3FFFFFFF, self.version, proto)


@dataclass
class Registration:
    key: ServiceKey
    port: int
    registered_at: float
    heartbeats: int = 0


class Portmapper:
    """Minimal PMAPPROC_SET / PMAPPROC_GETPORT service (RFC 1833)."""

    def __init__(self, tsap: int = WELL_KNOWN_TSAP_PORTMAP) -> None:
        self.tsap = tsap
        self.db: dict[ServiceKey, Registration] = {}
        self.call_log: list[dict] = []

    def set(self, key: ServiceKey, port: int) -> str:
        self.db[key] = Registration(key=key, port=port, registered_at=time.time())
        print(f"  [portmap] SET  {key.program!r} v{key.version}/{key.protocol} -> :{port}")
        return f"registered {key.program} v{key.version}/{key.protocol} on :{port}"

    def getport(self, key: ServiceKey) -> int:
        reg = self.db.get(key)
        port = reg.port if reg else 0
        rpc = key.rpc_id()
        self.call_log.append({"op": "GETPORT", "rpc": rpc, "port": port})
        print(
            f"  [portmap] GETPORT {key.program!r} v{key.version}/{key.protocol} "
            f"-> {port}  (rpc={rpc[0]} v{rpc[1]} proto={rpc[2]})"
        )
        return port

    def dump(self) -> list[dict]:
        return [
            {"rpc": reg.key.rpc_id(), "program": reg.key.program, "port": reg.port}
            for reg in self.db.values()
        ]

    def garbage_collect(self, ttl_seconds: float = 60.0) -> list[ServiceKey]:
        now = time.time()
        expired = [
            key for key, reg in self.db.items() if now - reg.registered_at > ttl_seconds
        ]
        for key in expired:
            del self.db[key]
            print(f"  [portmap] EXPIRED {key.program!r} (no heartbeat for {ttl_seconds}s)")
        return expired


@dataclass
class InetdService:
    tsap: int
    name: str
    spawn_count: int = 0
    connections: int = 0


class InetdSimulator:
    """The initial connection protocol of Figure 6-9.

    One process listens on many TSAPs. When a connection arrives on TSAP X,
    look up the service registered for X, fork, exec the daemon, and pass
    the connected FD to the child via FDs 0/1/2.
    """

    def __init__(self) -> None:
        self.services: dict[int, InetdService] = {}

    def register(self, tsap: int, name: str) -> None:
        self.services[tsap] = InetdService(tsap=tsap, name=name)
        print(f"  [inetd]   registered {name!r} on TSAP :{tsap}")

    def simulate_connection(self, tsap: int, peer: str) -> str:
        if tsap not in self.services:
            return f"[inetd]   no service registered for :{tsap} -> RST"
        svc = self.services[tsap]
        svc.connections += 1
        if svc.spawn_count == 0:
            svc.spawn_count += 1
            print(
                f"  [inetd]   CONNECTION from {peer} on :{tsap} "
                f"-> fork() and exec({svc.name!r})"
            )
            print(
                f"  [inetd]   child inherits FD 0/1/2 = the connected socket"
            )
            return f"[inetd]   spawned {svc.name} (cold start)"
        print(f"  [inetd]   CONNECTION from {peer} on :{tsap} -> reuse {svc.name}")
        return f"[inetd]   reused {svc.name}"

    def status(self) -> None:
        print()
        print("  Inetd service table (Figure 6-9 state):")
        for tsap, svc in self.services.items():
            print(
                f"    :{tsap:<5}  {svc.name:<16}  "
                f"connections={svc.connections}  spawns={svc.spawn_count}"
            )


def client_with_fallback(portmap: Portmapper, key: ServiceKey) -> None:
    print()
    print(f"  [client]  resolving {key.program!r} via the portmapper")
    port = portmap.getport(key)
    if port == 0:
        print("  [client]  portmapper returned 0 -- service is not registered")
        print("  [client]  fallback: try the IANA-assigned port from /etc/services")
        return
    print(f"  [client]  got port {port}; CONNECT(remote_NSAP, {port})")
    print(f"  [client]  three-way handshake -> ESTABLISHED on :{port}")


def main() -> None:
    print("=" * 72)
    print("PORTMAPPER  (RFC 1833 -- 'rpcbind')  +  INETD INITIAL CONNECTION")
    print("=" * 72)
    print(
        f"  Well-known TSAP of the portmapper: {WELL_KNOWN_TSAP_PORTMAP}/tcp+udp"
    )
    print(
        "  Well-known TSAP of inetd: 0 (it listens on a SET of ports at once)"
    )
    print()

    pm = Portmapper()
    pm.set(ServiceKey("BitTorrent", 1, "tcp"), port=6881)
    pm.set(ServiceKey("BackupAgent", 2, "tcp"), port=45000)
    pm.set(ServiceKey("NFS", 3, "udp"), port=2049)
    print()

    print("-" * 72)
    print("  DUMP (PMAPPROC_DUMP, useful for `rpcinfo -p` style inspection):")
    for entry in pm.dump():
        print(f"    rpc={entry['rpc'][0]:#x}  v{entry['rpc'][1]}  "
              f"proto={entry['rpc'][2]}  program={entry['program']!r}  "
              f"port={entry['port']}")
    print()

    print("-" * 72)
    print("  CLIENT RESOLUTION (PMAPPROC_GETPORT):")
    client_with_fallback(pm, ServiceKey("BitTorrent", 1, "tcp"))
    client_with_fallback(pm, ServiceKey("BackupAgent", 2, "tcp"))
    client_with_fallback(pm, ServiceKey("NotHere", 1, "tcp"))  # not registered
    print()

    print("=" * 72)
    print("INETD INITIAL CONNECTION PROTOCOL  (Tanenbaum Figure 6-9)")
    print("=" * 72)
    inetd = InetdSimulator()
    inetd.register(tsap=13, name="daytime")
    inetd.register(tsap=37, name="time")
    inetd.register(tsap=79, name="finger")
    inetd.register(tsap=6881, name="BitTorrent-spawn")
    print()
    inetd.simulate_connection(13, "10.0.0.2:54321")
    inetd.simulate_connection(13, "10.0.0.3:54322")
    inetd.simulate_connection(6881, "10.0.0.4:55000")
    inetd.simulate_connection(9999, "10.0.0.5:60000")  # not registered
    inetd.status()
    print()
    print("=" * 72)
    print("Lesson complete. See docs/en.md for the full TSAP/NSAP discussion,")
    print("RFC 1833 wire-format details, and DNS SRV as the modern portmap.")
    print("=" * 72)


if __name__ == "__main__":
    main()
