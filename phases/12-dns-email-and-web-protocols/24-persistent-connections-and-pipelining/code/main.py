#!/usr/bin/env python3
"""HTTP/1.0 vs HTTP/1.1 vs pipelined latency simulator (RFC 1945 / RFC 7230 / RFC 7540).

Simulates the wall-clock cost of fetching N resources under three strategies:
HTTP/1.0 (one TCP connection per request), HTTP/1.1 persistent (one connection,
sequential), and HTTP/1.1 pipelined (one connection, requests sent back-to-back).
The HTTP/2 case (RFC 7540) is shown as the lower bound. All values are
simplified for pedagogy.

Run with `python3 main.py`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Latency:
    rtt_ms: int
    body_ms: int
    slow_start_rtt: int


DEFAULT = Latency(rtt_ms=50, body_ms=20, slow_start_rtt=3)


def http10(n: int, lat: Latency = DEFAULT) -> int:
    handshake_per_req = 2 * lat.rtt_ms + lat.slow_start_rtt * lat.rtt_ms
    return n * (handshake_per_req + lat.rtt_ms + lat.body_ms)


def http11_persistent(n: int, lat: Latency = DEFAULT) -> int:
    handshake = 2 * lat.rtt_ms + lat.slow_start_rtt * lat.rtt_ms
    per_request = lat.rtt_ms + lat.body_ms
    return handshake + n * per_request


def http11_pipelined(n: int, lat: Latency = DEFAULT) -> int:
    handshake = 2 * lat.rtt_ms + lat.slow_start_rtt * lat.rtt_ms
    return handshake + n * lat.rtt_ms + n * lat.body_ms


def http2_multiplexed(n: int, lat: Latency = DEFAULT) -> int:
    handshake = 2 * lat.rtt_ms + lat.slow_start_rtt * lat.rtt_ms
    return handshake + lat.rtt_ms + n * lat.body_ms


def chunked_encode(chunks: list[bytes]) -> bytes:
    """RFC 7230 §4.1 chunked transfer encoding."""
    out = bytearray()
    for chunk in chunks:
        out.extend(f"{len(chunk):x}\r\n".encode())
        out.extend(chunk)
        out.extend(b"\r\n")
    out.extend(b"0\r\n\r\n")
    return bytes(out)


def chunked_decode(data: bytes) -> list[bytes]:
    out: list[bytes] = []
    i = 0
    while i < len(data):
        line_end = data.index(b"\r\n", i)
        size = int(data[i:line_end], 16)
        if size == 0:
            break
        out.append(data[line_end + 2 : line_end + 2 + size])
        i = line_end + 2 + size + 2
    return out


def main() -> None:
    print("=" * 64)
    print("PERSISTENT CONNECTIONS + PIPELINING  --  RFC 1945 / 7230 / 7540")
    print("=" * 64)

    lat = Latency(rtt_ms=50, body_ms=20, slow_start_rtt=3)
    print(f"\nNetwork model: RTT={lat.rtt_ms} ms  body per request={lat.body_ms} ms  "
          f"slow-start RTTs={lat.slow_start_rtt}")

    for n in (5, 20, 40):
        a = http10(n, lat)
        b = http11_persistent(n, lat)
        c = http11_pipelined(n, lat)
        d = http2_multiplexed(n, lat)
        print(f"\nN={n} resources")
        print(f"  HTTP/1.0 one-conn-per-req : {a:>5} ms")
        print(f"  HTTP/1.1 persistent       : {b:>5} ms   (saved {a - b} ms)")
        print(f"  HTTP/1.1 pipelined        : {c:>5} ms   (saved {a - c} ms vs HTTP/1.0)")
        print(f"  HTTP/2 multiplexed (h2)   : {d:>5} ms   (saved {a - d} ms vs HTTP/1.0)")

    print("\nChunked transfer encoding (RFC 7230 §4.1):")
    chunks = [b"first part ", b"second part ", b"final"]
    encoded = chunked_encode(chunks)
    print(f"  encoded: {encoded!r}")
    decoded = chunked_decode(encoded)
    print(f"  decoded: {decoded}")


if __name__ == "__main__":
    main()
