#!/usr/bin/env python3
"""HTTP header parser, content negotiator, and cookie-jar helper (RFC 7230 / 6265).

Parses an HTTP header block into a case-insensitive dict, classifies each
header by category, picks the best media type from the Accept header, and
builds a properly-scoped Set-Cookie value.

Run with `python3 main.py`.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


HEADER_CATEGORIES = {
    "host": "identity",
    "user-agent": "identity",
    "authorization": "auth",
    "www-authenticate": "auth",
    "accept": "negotiation",
    "accept-charset": "negotiation",
    "accept-encoding": "negotiation",
    "accept-language": "negotiation",
    "content-type": "body",
    "content-length": "body",
    "content-encoding": "body",
    "content-language": "body",
    "content-range": "body",
    "content-disposition": "body",
    "cookie": "state",
    "set-cookie": "state",
    "cache-control": "cache",
    "expires": "cache",
    "last-modified": "cache",
    "etag": "cache",
    "if-none-match": "cache",
    "if-modified-since": "cache",
    "age": "cache",
    "vary": "cache",
    "connection": "connection",
    "upgrade": "connection",
    "transfer-encoding": "connection",
    "referer": "routing",
    "location": "routing",
}


@dataclass
class MediaRange:
    media_type: str
    q: float = 1.0


def parse_headers(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in text.splitlines():
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        out[k.strip().lower()] = v.strip()
    return out


def categorize(headers: Dict[str, str]) -> Dict[str, List[Tuple[str, str]]]:
    out: Dict[str, List[Tuple[str, str]]] = {}
    for k, v in headers.items():
        cat = HEADER_CATEGORIES.get(k.lower(), "other")
        out.setdefault(cat, []).append((k, v))
    return out


def parse_accept(accept: str) -> List[MediaRange]:
    ranges: List[MediaRange] = []
    for chunk in accept.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        q = 1.0
        if ";q=" in chunk:
            mt, _, qpart = chunk.partition(";q=")
            try:
                q = float(qpart.split(";", 1)[0])
            except ValueError:
                q = 1.0
            chunk = mt.strip()
        ranges.append(MediaRange(media_type=chunk, q=q))
    return sorted(ranges, key=lambda r: -r.q)


def pick_media_type(accept: str, available: List[str]) -> Optional[str]:
    ranges = parse_accept(accept)
    for r in ranges:
        if r.media_type == "*/*" or r.media_type == available[0].split(";")[0]:
            return available[0]
    return None


def build_set_cookie(
    name: str,
    value: str,
    *,
    domain: Optional[str] = None,
    path: str = "/",
    secure: bool = False,
    httponly: bool = False,
    samesite: str = "Lax",
    max_age: Optional[int] = None,
) -> str:
    parts = [f"{name}={value}"]
    if domain:
        parts.append(f"Domain={domain}")
    parts.append(f"Path={path}")
    if max_age is not None:
        parts.append(f"Max-Age={max_age}")
    if secure:
        parts.append("Secure")
    if httponly:
        parts.append("HttpOnly")
    if samesite:
        parts.append(f"SameSite={samesite}")
    return "; ".join(parts)


def basic_auth_header(user: str, password: str) -> str:
    payload = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {payload}"


SAMPLE_HEADERS = """\
Host: example.com
User-Agent: curl/8.5.0
Accept: text/html, application/xhtml+xml;q=0.9, application/json;q=0.8, */*;q=0.5
Accept-Encoding: gzip, br;q=0.9
Accept-Language: en-US,en;q=0.9,ja;q=0.5
Authorization: Basic dXNlcjpwYXNz
Cookie: sid=abc123; theme=dark
Cache-Control: max-age=300
If-None-Match: "5e9c1a3a-1f0"
Referer: https://www.google.com/
Connection: keep-alive
"""


def main() -> None:
    print("=" * 64)
    print("HTTP HEADERS, COOKIES, CONTENT NEGOTIATION  --  RFC 7230 / 6265")
    print("=" * 64)

    headers = parse_headers(SAMPLE_HEADERS)
    print(f"\nParsed {len(headers)} headers from sample block.")
    by_cat = categorize(headers)
    for cat in sorted(by_cat):
        print(f"  [{cat}]")
        for k, v in by_cat[cat]:
            print(f"    {k}: {v}")

    print("\nContent negotiation (Accept):")
    accept = headers.get("accept", "")
    ranges = parse_accept(accept)
    for r in ranges:
        print(f"  media-type={r.media_type:<32}  q={r.q}")
    chosen = pick_media_type(accept, ["text/html; charset=UTF-8"])
    print(f"  server picks: {chosen}")

    print("\nCookie: Set-Cookie builder (RFC 6265):")
    print(f"  {build_set_cookie('sid', 'xyz789', domain='example.com', httponly=True, samesite='Lax', max_age=3600, secure=True)}")

    print("\nBasic auth header (RFC 7617):")
    print(f"  {basic_auth_header('alice', 's3cret')}")


if __name__ == "__main__":
    main()
