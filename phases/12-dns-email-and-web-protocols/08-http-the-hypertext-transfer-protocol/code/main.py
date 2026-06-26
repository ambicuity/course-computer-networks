#!/usr/bin/env python3
"""HTTP protocol parser: requests, responses, headers, chunked transfer.

Stdlib only, no network calls. Demonstrates four things:

1. HTTP request parsing: the request line (method + URL + HTTP/1.1)
   and request headers (Host, User-Agent, Accept, Cookie, etc.) from
   section 7.3.4 and Fig. 7-37 (GET, HEAD, POST, PUT, DELETE, TRACE,
   CONNECT, OPTIONS).
2. HTTP response parsing: status line (code + reason), response
   headers (Content-Type, Content-Length, Set-Cookie, Cache-Control,
   ETag, Last-Modified, Server, Location), and the status code groups
   (1xx-5xx) from Fig. 7-38.
3. Message header model: the full header list from Fig. 7-39, showing
   request-only, response-only, and both-direction headers, plus
   cookie handling (Set-Cookie / Cookie).
4. Chunked transfer-encoding decoder: assembling chunked bodies from
   Transfer-Encoding: chunked responses, including chunk-size parsing
   and trailing headers.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


HTTP_METHODS: dict[str, str] = {
    "GET": "Read a Web page",
    "HEAD": "Read a Web page's header",
    "POST": "Append to a Web page",
    "PUT": "Store a Web page",
    "DELETE": "Remove the Web page",
    "TRACE": "Echo the incoming request",
    "CONNECT": "Connect through a proxy",
    "OPTIONS": "Query options for a page",
}

STATUS_GROUPS: dict[int, str] = {
    1: "Information",
    2: "Success",
    3: "Redirection",
    4: "Client error",
    5: "Server error",
}

STATUS_CODES: dict[int, str] = {
    100: "Continue",
    200: "OK",
    204: "No content",
    301: "Moved permanently",
    302: "Found (redirect)",
    304: "Not modified",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not found",
    500: "Internal server error",
    503: "Service unavailable",
}

REQUEST_HEADERS: dict[str, str] = {
    "User-Agent": "Information about the browser and its platform",
    "Accept": "The type of pages the client can handle",
    "Accept-Charset": "The character sets that are acceptable",
    "Accept-Encoding": "The page encodings the client can handle",
    "Accept-Language": "The natural languages the client can handle",
    "If-Modified-Since": "Time and date to check freshness",
    "If-None-Match": "Previously sent tags to check freshness",
    "Host": "The server's DNS name (mandatory)",
    "Authorization": "A list of the client's credentials",
    "Referer": "The previous URL from which the request came",
    "Cookie": "Previously set cookie sent back to the server",
}

RESPONSE_HEADERS: dict[str, str] = {
    "Set-Cookie": "Cookie for the client to store",
    "Server": "Information about the server",
    "Content-Encoding": "How the content is encoded (e.g., gzip)",
    "Content-Language": "The natural language used in the page",
    "Content-Length": "The page's length in bytes",
    "Content-Type": "The page's MIME type",
    "Content-Range": "Identifies a portion of the page's content",
    "Last-Modified": "Time and date the page was last changed",
    "Expires": "Time and date when the page stops being valid",
    "Location": "Tells the client where to send its request",
    "Accept-Ranges": "Indicates the server will accept byte range requests",
}

BOTH_HEADERS: dict[str, str] = {
    "Date": "Date and time the message was sent",
    "Range": "Identifies a portion of a page",
    "Cache-Control": "Directives for how to treat caches",
    "ETag": "Tag for the contents of the page",
    "Upgrade": "The protocol the sender wants to switch to",
}


@dataclass
class HTTPRequest:
    method: str
    url: str
    version: str
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""

    @property
    def host(self) -> str:
        return self.headers.get("Host", "")

    @property
    def is_keep_alive(self) -> bool:
        conn = self.headers.get("Connection", "").lower()
        return "keep-alive" in conn or (self.version == "HTTP/1.1" and "close" not in conn)

    @classmethod
    def parse(cls, raw: str) -> "HTTPRequest":
        lines = raw.splitlines()
        if not lines:
            raise ValueError("empty request")
        parts = lines[0].split()
        if len(parts) != 3:
            raise ValueError(f"bad request line: {lines[0]}")
        method, url, version = parts
        headers: dict[str, str] = {}
        i = 1
        while i < len(lines) and lines[i]:
            name, _, value = lines[i].partition(":")
            headers[name.strip()] = value.strip()
            i += 1
        body = "\n".join(lines[i + 1:])
        return cls(method, url, version, headers, body)


@dataclass
class HTTPResponse:
    version: str
    status_code: int
    reason: str
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""

    @property
    def status_group(self) -> int:
        return self.status_code // 100

    @property
    def content_type(self) -> str:
        return self.headers.get("Content-Type", "application/octet-stream")

    @property
    def content_length(self) -> int:
        return int(self.headers.get("Content-Length", "0"))

    @property
    def is_chunked(self) -> bool:
        return self.headers.get("Transfer-Encoding", "").lower() == "chunked"

    @classmethod
    def parse(cls, raw: str) -> "HTTPResponse":
        lines = raw.splitlines()
        if not lines:
            raise ValueError("empty response")
        parts = lines[0].split(None, 2)
        if len(parts) != 3:
            raise ValueError(f"bad status line: {lines[0]}")
        version, code, reason = parts
        headers: dict[str, str] = {}
        i = 1
        while i < len(lines) and lines[i]:
            name, _, value = lines[i].partition(":")
            headers[name.strip()] = value.strip()
            i += 1
        body = "\n".join(lines[i + 1:])
        return cls(version, int(code), reason, headers, body)

    def format(self) -> str:
        lines = [f"{self.version} {self.status_code} {self.reason}"]
        for k, v in self.headers.items():
            lines.append(f"{k}: {v}")
        lines.append("")
        if self.body:
            lines.append(self.body)
        return "\n".join(lines)


def decode_chunked(chunked_body: str) -> tuple[str, list[str]]:
    """Decode an HTTP chunked transfer-encoding body.

    Each chunk is: hex-size CRLF data CRLF. The final chunk has size 0
    followed by optional trailing headers and a final CRLF.
    Returns (decoded_body, trailing_headers).
    """
    pos = 0
    decoded_parts: list[str] = []
    trailing: list[str] = []
    data = chunked_body.encode()

    while pos < len(data):
        crlf = data.find(b"\n", pos)
        if crlf == -1:
            break
        size_line = data[pos:crlf].strip()
        pos = crlf + 1
        if b";" in size_line:
            size_line = size_line.split(b";")[0].strip()
        try:
            chunk_size = int(size_line, 16)
        except ValueError:
            continue
        if chunk_size == 0:
            while pos < len(data):
                end = data.find(b"\n", pos)
                if end == -1:
                    break
                line = data[pos:end].strip()
                if line:
                    trailing.append(line.decode())
                pos = end + 1
            break
        chunk_data = data[pos:pos + chunk_size]
        decoded_parts.append(chunk_data.decode(errors="replace"))
        pos += chunk_size
        while pos < len(data) and data[pos:pos + 1] in (b"\r", b"\n"):
            pos += 1
    return "".join(decoded_parts), trailing


def build_response(status: int, body: str, extra_headers: Optional[dict[str, str]] = None) -> HTTPResponse:
    headers = {
        "Content-Type": "text/html",
        "Content-Length": str(len(body)),
        "Server": "SimHTTP/1.0",
    }
    if extra_headers:
        headers.update(extra_headers)
    return HTTPResponse("HTTP/1.1", status, STATUS_CODES.get(status, "Unknown"),
                        headers, body)


def main() -> None:
    print("=" * 70)
    print("HTTP Methods (Fig. 7-37)")
    print("=" * 70)
    for method, desc in HTTP_METHODS.items():
        print(f"  {method:<10} {desc}")

    print(f"\n{'=' * 70}")
    print("HTTP Request Parsing")
    print(f"{'=' * 70}")

    get_request = """\
GET /index.html HTTP/1.1
Host: www.cs.washington.edu
User-Agent: Mozilla/5.0 (X11; Linux x86_64) Chrome/5.0.375.125
Accept: text/html,application/xhtml+xml
Accept-Language: en-US,en;q=0.9
Accept-Encoding: gzip,deflate
Connection: keep-alive
Cookie: sessionID=abc123; prefs=dark

"""
    print("\n--- GET request ---")
    req = HTTPRequest.parse(get_request)
    print(f"  Method:  {req.method}")
    print(f"  URL:     {req.url}")
    print(f"  Version: {req.version}")
    print(f"  Host:    {req.host}")
    print(f"  Keep-alive: {req.is_keep_alive}")
    print(f"  Headers ({len(req.headers)}):")
    for k, v in req.headers.items():
        print(f"    {k}: {v}")

    post_request = """\
POST /cgi-bin/order.cgi HTTP/1.1
Host: widget.com
Content-Type: application/x-www-form-urlencoded
Content-Length: 89

customer=John+Doe&address=100+Main+St.&city=White+Plains&state=NY&cc=mastercard
"""
    print("\n--- POST request ---")
    post_req = HTTPRequest.parse(post_request)
    print(f"  Method:  {post_req.method}")
    print(f"  URL:     {post_req.url}")
    print(f"  Content-Type: {post_req.headers.get('Content-Type', '')}")
    print(f"  Content-Length: {post_req.headers.get('Content-Length', '')}")
    print(f"  Body: {post_req.body}")

    put_request = """\
PUT /new-page.html HTTP/1.1
Host: www.example.com
Content-Type: text/html
Content-Length: 42
Authorization: Bearer abc123def456

<html><body>New page content</body></html>
"""
    print("\n--- PUT request ---")
    put_req = HTTPRequest.parse(put_request)
    print(f"  Method:  {put_req.method}")
    print(f"  URL:     {put_req.url}")
    print(f"  Auth:    {put_req.headers.get('Authorization', '')}")

    print(f"\n{'=' * 70}")
    print("HTTP Response Parsing")
    print(f"{'=' * 70}")

    print("\n--- 200 OK response ---")
    resp200 = build_response(200, "<html><body>Hello, World!</body></html>",
                              {"Cache-Control": "max-age=3600",
                               "ETag": '"abc123"',
                               "Last-Modified": "Mon, 01 Jan 2024 00:00:00 GMT"})
    print(f"  Status: {resp200.status_code} {resp200.reason}")
    print(f"  Group:  {resp200.status_group}xx ({STATUS_GROUPS.get(resp200.status_group, '')})")
    print(f"  Content-Type: {resp200.content_type}")
    print(f"  Content-Length: {resp200.content_length}")
    print(f"  Is chunked: {resp200.is_chunked}")
    print(f"  Full response:")
    for line in resp200.format().splitlines():
        print(f"    | {line}")

    print("\n--- 301 redirect response ---")
    resp301 = build_response(301, "", {"Location": "http://www.new-site.com/"})
    print(f"  Status: {resp301.status_code} {resp301.reason}")
    print(f"  Location: {resp301.headers.get('Location', '')}")

    print("\n--- 404 not found response ---")
    resp404 = build_response(404, "<html><body>404 Not Found</body></html>")
    print(f"  Status: {resp404.status_code} {resp404.reason}")

    print("\n--- 500 server error response ---")
    resp500 = build_response(500, "<html><body>Internal Server Error</body></html>")
    print(f"  Status: {resp500.status_code} {resp500.reason}")

    print("\n--- Set-Cookie header ---")
    resp_cookie = build_response(200, "<html><body>Welcome</body></html>",
                                  {"Set-Cookie": "sessionID=abc123; Path=/; Expires=Wed, 09 Jun 2025 10:18:14 GMT; Secure"})
    print(f"  Set-Cookie: {resp_cookie.headers.get('Set-Cookie', '')}")
    print(f"  -> Browser stores this and sends it back as Cookie: sessionID=abc123")

    print(f"\n{'=' * 70}")
    print("HTTP Status Code Groups (Fig. 7-38)")
    print(f"{'=' * 70}")
    for group, name in STATUS_GROUPS.items():
        examples = [f"{code}" for code in STATUS_CODES if code // 100 == group]
        print(f"  {group}xx {name:<20} examples: {', '.join(examples[:4])}")

    print(f"\n{'=' * 70}")
    print("HTTP Message Headers (Fig. 7-39)")
    print(f"{'=' * 70}")
    print("\n  Request-only headers:")
    for h, d in REQUEST_HEADERS.items():
        print(f"    {h:<22} {d}")
    print("\n  Response-only headers:")
    for h, d in RESPONSE_HEADERS.items():
        print(f"    {h:<22} {d}")
    print("\n  Both-direction headers:")
    for h, d in BOTH_HEADERS.items():
        print(f"    {h:<22} {d}")

    print(f"\n{'=' * 70}")
    print("Chunked Transfer-Encoding Decoder")
    print(f"{'=' * 70}")

    chunked_raw = "HTTP/1.1 200 OK\r\n"
    chunked_raw += "Content-Type: text/html\r\n"
    chunked_raw += "Transfer-Encoding: chunked\r\n"
    chunked_raw += "\r\n"
    chunked_raw += "5\r\nHello\r\n"
    chunked_raw += "1\r\n \r\n"
    chunked_raw += "5\r\nWorld\r\n"
    chunked_raw += "1\r\n!\r\n"
    chunked_raw += "0\r\n"
    chunked_raw += "Trailer: value-here\r\n"
    chunked_raw += "\r\n"

    print("\n  Raw chunked response:")
    for line in chunked_raw.splitlines():
        print(f"    | {line}")

    raw_resp = HTTPResponse.parse(chunked_raw)
    print(f"\n  Parsed: {raw_resp.status_code} {raw_resp.reason}")
    print(f"  Transfer-Encoding: {raw_resp.headers.get('Transfer-Encoding', '(none)')}")
    print(f"  Is chunked: {raw_resp.is_chunked}")

    decoded, trailers = decode_chunked(raw_resp.body)
    print(f"\n  Decoded body: {decoded!r}")
    print(f"  Trailing headers: {trailers}")

    print(f"\n  Chunked encoding explained:")
    print(f"    1. Each chunk starts with a hex size line")
    print(f"    2. Followed by exactly that many bytes of data")
    print(f"    3. A zero-size chunk (0) marks the end")
    print(f"    4. Optional trailing headers follow the final chunk")

    print(f"\n{'=' * 70}")
    print("HTTP Connections (section 7.3.4)")
    print(f"{'=' * 70}")
    print("  HTTP/1.0: one request per TCP connection")
    print("  HTTP/1.1: persistent connections (connection reuse)")
    print("  HTTP/1.1: pipelined requests (send req 2 before resp 1 arrives)")
    print("  Trade-off: keep-alive saves TCP setup, but server must decide when to close")


if __name__ == "__main__":
    main()