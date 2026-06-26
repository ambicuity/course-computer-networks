#!/usr/bin/env python3
"""HTTP method and status code classifier (RFC 7230 / RFC 7231 / RFC 9110).

Parses an HTTP request line and a response status line, classifies the method
by safety and idempotency, classifies the status code into its 1xx..5xx class,
and prints a small reference table. No network calls.

Run with `python3 main.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
IDEMPOTENT_METHODS = {"GET", "HEAD", "PUT", "DELETE", "OPTIONS", "TRACE"}

STATUS_NAMES = {
    100: "Continue",
    101: "Switching Protocols",
    200: "OK",
    201: "Created",
    204: "No Content",
    206: "Partial Content",
    301: "Moved Permanently",
    302: "Found",
    303: "See Other",
    304: "Not Modified",
    307: "Temporary Redirect",
    308: "Permanent Redirect",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    409: "Conflict",
    410: "Gone",
    418: "I'm a Teapot (RFC 2324)",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
}


@dataclass(frozen=True)
class RequestLine:
    method: str
    target: str
    version: str


@dataclass(frozen=True)
class StatusLine:
    version: str
    code: int
    reason: str


def parse_request_line(line: str) -> RequestLine:
    parts = line.rstrip("\r\n").split(" ", 2)
    if len(parts) != 3:
        raise ValueError(f"not a request line: {line!r}")
    return RequestLine(method=parts[0], target=parts[1], version=parts[2])


def parse_status_line(line: str) -> StatusLine:
    parts = line.rstrip("\r\n").split(" ", 2)
    if len(parts) < 2:
        raise ValueError(f"not a status line: {line!r}")
    return StatusLine(version=parts[0], code=int(parts[1]), reason=parts[2] if len(parts) > 2 else "")


def classify_status(code: int) -> str:
    if 100 <= code < 200:
        return "1xx informational"
    if 200 <= code < 300:
        return "2xx success"
    if 300 <= code < 400:
        return "3xx redirection"
    if 400 <= code < 500:
        return "4xx client error"
    if 500 <= code < 600:
        return "5xx server error"
    raise ValueError(f"not a valid HTTP status code: {code}")


def is_safe(method: str) -> bool:
    return method.upper() in SAFE_METHODS


def is_idempotent(method: str) -> bool:
    return method.upper() in IDEMPOTENT_METHODS


def main() -> None:
    print("=" * 64)
    print("HTTP METHODS AND STATUS CODES  --  RFC 7230 / 7231 / 9110")
    print("=" * 64)

    print("\nRequest line parsing:")
    for line in (
        "GET /index.html HTTP/1.1",
        "POST /api/items HTTP/1.1",
        "OPTIONS * HTTP/2",
    ):
        r = parse_request_line(line)
        safe = "safe" if is_safe(r.method) else "unsafe"
        idem = "idempotent" if is_idempotent(r.method) else "non-idempotent"
        print(f"  {line!r:<32}  -> method={r.method:<8} target={r.target:<14} version={r.version}  ({safe}, {idem})")

    print("\nStatus line parsing:")
    for line in (
        "HTTP/1.1 200 OK",
        "HTTP/1.1 404 Not Found",
        "HTTP/1.1 504 Gateway Timeout",
        "HTTP/1.1 418 \r\n",
    ):
        try:
            s = parse_status_line(line)
            cls = classify_status(s.code)
            name = STATUS_NAMES.get(s.code, "?")
            print(f"  {line!r:<32}  -> {s.code} {name}  ({cls})")
        except ValueError as e:
            print(f"  {line!r:<32}  -> ERROR {e}")

    print("\nStatus code reference:")
    for code, name in STATUS_NAMES.items():
        print(f"  {code:>3}  {classify_status(code):<22}  {name}")

    print("\nMethod safety / idempotency:")
    for method in ("GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "CONNECT", "OPTIONS", "TRACE"):
        s = "safe" if is_safe(method) else "not safe"
        i = "idempotent" if is_idempotent(method) else "non-idempotent"
        print(f"  {method:<8} {s:<10} {i}")


if __name__ == "__main__":
    main()
