#!/usr/bin/env python3
"""CGI request handler simulator (RFC 3875 / CGI 1.1).

Implements the Common Gateway Interface model from scratch:
parse a raw HTTP request, build the CGI/1.1 environment variable set,
invoke a Python function that reads those env vars and a stdin bytes
buffer and writes a dynamic HTML response to its stdout buffer, then
wrap the script output in a complete HTTP/1.1 response.  Demonstrates
both GET (query string) and POST (form body) scenarios, the per-request
fork overhead cost model, and the SSR vs CSR comparison.

Run with `python3 main.py`.
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# HTTP request parser
# ---------------------------------------------------------------------------

@dataclass
class HttpRequest:
    method: str
    path: str
    query_string: str
    http_version: str
    headers: Dict[str, str]
    body: bytes


def parse_http_request(raw: str) -> HttpRequest:
    """Parse a raw HTTP/1.x request string into an HttpRequest dataclass."""
    if "\r\n\r\n" in raw:
        head, _, body_str = raw.partition("\r\n\r\n")
    else:
        head = raw
        body_str = ""

    lines = head.split("\r\n")
    parts = lines[0].split(" ", 2)
    method = parts[0] if len(parts) > 0 else "GET"
    raw_target = parts[1] if len(parts) > 1 else "/"
    http_version = parts[2] if len(parts) > 2 else "HTTP/1.0"

    if "?" in raw_target:
        path, _, query_string = raw_target.partition("?")
    else:
        path = raw_target
        query_string = ""

    headers: Dict[str, str] = {}
    for line in lines[1:]:
        if ": " in line:
            name, _, value = line.partition(": ")
            headers[name.lower()] = value

    body = body_str.encode("latin-1")
    return HttpRequest(
        method=method,
        path=path,
        query_string=query_string,
        http_version=http_version,
        headers=headers,
        body=body,
    )


# ---------------------------------------------------------------------------
# CGI environment builder  (RFC 3875 §4.1)
# ---------------------------------------------------------------------------

def build_cgi_env(
    req: HttpRequest,
    server_name: str = "localhost",
    server_port: int = 8080,
    remote_addr: str = "127.0.0.1",
    script_name: str = "/cgi-bin/app.py",
) -> Dict[str, str]:
    """Build a CGI/1.1 environment variable dict from an HttpRequest.

    Implements RFC 3875 §4.1.  The resulting dict is what the server
    would pass to os.execve() as the environment when spawning the
    CGI script process.
    """
    env: Dict[str, str] = {
        "GATEWAY_INTERFACE": "CGI/1.1",       # §4.1.4
        "REQUEST_METHOD":    req.method,        # §4.1.12
        "SCRIPT_NAME":       script_name,       # §4.1.13
        "PATH_INFO":         "",                # §4.1.9  (no extra path here)
        "QUERY_STRING":      req.query_string,  # §4.1.7
        "SERVER_NAME":       server_name,       # §4.1.14
        "SERVER_PORT":       str(server_port),  # §4.1.15
        "SERVER_PROTOCOL":   req.http_version,  # §4.1.16
        "SERVER_SOFTWARE":   "PyCGI/0.1",       # §4.1.17
        "REMOTE_ADDR":       remote_addr,       # §4.1.8
    }

    # §4.1.2 + §4.1.3: CONTENT_LENGTH and CONTENT_TYPE for request bodies
    if req.method in ("POST", "PUT", "PATCH"):
        if "content-type" in req.headers:
            env["CONTENT_TYPE"] = req.headers["content-type"]
        body_len = (
            str(len(req.body))
            if req.body
            else req.headers.get("content-length", "0")
        )
        env["CONTENT_LENGTH"] = body_len

    # §4.1.18: HTTP_* — each request header becomes HTTP_HEADER_NAME
    for name, value in req.headers.items():
        cgi_name = "HTTP_" + name.upper().replace("-", "_")
        env[cgi_name] = value

    return env


# ---------------------------------------------------------------------------
# CGI script (runs "inside" the spawned process)
# ---------------------------------------------------------------------------

def cgi_script(env: Dict[str, str], stdin: bytes) -> bytes:
    """Simulate a CGI script: read env + stdin, write HTTP response to stdout.

    In production the server would os.fork() + os.execve() a real file.
    Here we simulate exec() by calling this function directly and treating
    its return value as the bytes the script wrote to stdout.

    The output format is: CGI response headers + blank line + body.
    The gateway (cgi_gateway below) prepends the HTTP status line.
    """
    method = env.get("REQUEST_METHOD", "GET")
    query_string = env.get("QUERY_STRING", "")
    content_length = int(env.get("CONTENT_LENGTH", "0") or "0")
    content_type = env.get("CONTENT_TYPE", "")

    # Parse GET parameters from QUERY_STRING
    get_params: Dict[str, List[str]] = urllib.parse.parse_qs(query_string)

    # Parse POST body from stdin
    post_params: Dict[str, List[str]] = {}
    if method == "POST" and "application/x-www-form-urlencoded" in content_type:
        body_str = stdin[:content_length].decode("utf-8", errors="replace")
        post_params = urllib.parse.parse_qs(body_str)

    def first(d: Dict[str, List[str]], key: str, default: str = "") -> str:
        return d[key][0] if key in d else default

    name = first(post_params, "name") or first(get_params, "name")
    color = first(post_params, "color") or first(get_params, "color") or "#0077cc"
    greeting = f"Hello, {name}!" if name else "Hello, World!"

    # Build the dynamic HTML — proof of server-side generation
    table_rows = "".join(
        f"    <tr><td>{k}</td><td>{env.get(k, '')}</td></tr>\n"
        for k in (
            "GATEWAY_INTERFACE", "REQUEST_METHOD", "SCRIPT_NAME",
            "QUERY_STRING", "CONTENT_TYPE", "CONTENT_LENGTH",
            "SERVER_NAME", "SERVER_PORT", "REMOTE_ADDR",
        )
    )
    html_body = (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="UTF-8">\n'
        f"  <title>CGI Demo: {greeting}</title>\n"
        "  <style>\n"
        f"    body {{ font-family: sans-serif; background: {color}22; padding: 2em; }}\n"
        f"    h1   {{ color: {color}; }}\n"
        "    table { border-collapse: collapse; font-size: 0.9em; }\n"
        "    td, th { border: 1px solid #ccc; padding: 0.4em 0.8em; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        f"  <h1>{greeting}</h1>\n"
        "  <p>Dynamically generated by CGI script app.py at request time.</p>\n"
        "  <h2>CGI Environment (RFC 3875 §4.1)</h2>\n"
        "  <table>\n"
        "    <tr><th>Variable</th><th>Value</th></tr>\n"
        + table_rows
        + "  </table>\n"
        "</body>\n"
        "</html>\n"
    )

    body_bytes = html_body.encode("utf-8")

    # CGI script writes: headers, blank line, body  (RFC 3875 §6.3.1)
    cgi_headers = (
        "Content-Type: text/html; charset=utf-8\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        "X-CGI-Script: app.py\r\n"
        "\r\n"
    ).encode("latin-1")

    return cgi_headers + body_bytes


# ---------------------------------------------------------------------------
# Minimal CGI gateway (simulates the web server / Apache mod_cgi side)
# ---------------------------------------------------------------------------

def cgi_gateway(
    raw_request: str,
    server_name: str = "localhost",
    server_port: int = 8080,
    remote_addr: str = "127.0.0.1",
) -> Tuple[bytes, Dict[str, str]]:
    """Simulate a CGI gateway executing a request.

    Steps (RFC 3875 §4):
      1. Parse the HTTP request.
      2. Build the CGI environment.
      3. Call cgi_script() — stands in for fork()+exec().
      4. Prepend the HTTP/1.1 status line to the script stdout output.
    Returns (full_http_response_bytes, cgi_env_dict).
    """
    req = parse_http_request(raw_request)
    env = build_cgi_env(
        req,
        server_name=server_name,
        server_port=server_port,
        remote_addr=remote_addr,
    )
    script_stdout = cgi_script(env, req.body)
    # Gateway prepends the HTTP status line (script only writes CGI headers)
    http_response = b"HTTP/1.1 200 OK\r\n" + script_stdout
    return http_response, env


# ---------------------------------------------------------------------------
# Client-side rendering: JSON API model
# ---------------------------------------------------------------------------

def client_side_api_response(query: str) -> Dict[str, object]:
    """Return a JSON API payload a CSR app would fetch and render in the browser."""
    results = [
        {"id": 1, "title": f"Result A for '{query}'", "score": 0.95},
        {"id": 2, "title": f"Result B for '{query}'", "score": 0.82},
        {"id": 3, "title": f"Result C for '{query}'", "score": 0.71},
    ]
    return {
        "query": query,
        "count": len(results),
        "results": results,
        "render": "client-side",
    }


# ---------------------------------------------------------------------------
# Pretty-print helper
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'=' * 64}")
    print(f"  {title}")
    print("=" * 64)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 64)
    print("CGI / SERVER-SIDE vs CLIENT-SIDE WEB APPS  --  RFC 3875")
    print("=" * 64)

    # -----------------------------------------------------------------------
    # 1. Parse a raw HTTP GET request
    # -----------------------------------------------------------------------
    section("1. PARSE HTTP GET REQUEST")
    get_raw = (
        "GET /cgi-bin/app.py?name=Alice&color=%230077cc HTTP/1.1\r\n"
        "Host: localhost:8080\r\n"
        "User-Agent: Demo/1.0\r\n"
        "Accept: text/html,application/xhtml+xml\r\n"
        "Connection: keep-alive\r\n"
        "\r\n"
    )
    req_get = parse_http_request(get_raw)
    print(f"  Method        : {req_get.method}")
    print(f"  Path          : {req_get.path}")
    print(f"  Query string  : {req_get.query_string}")
    print(f"  HTTP version  : {req_get.http_version}")
    print("  Headers       :")
    for k, v in req_get.headers.items():
        print(f"    {k}: {v}")

    # -----------------------------------------------------------------------
    # 2. Build CGI environment from the GET request
    # -----------------------------------------------------------------------
    section("2. CGI ENVIRONMENT VARIABLES  (RFC 3875 §4.1)")
    env_get = build_cgi_env(req_get)
    important_keys = [
        "GATEWAY_INTERFACE", "REQUEST_METHOD", "SCRIPT_NAME",
        "PATH_INFO", "QUERY_STRING", "SERVER_NAME", "SERVER_PORT",
        "SERVER_PROTOCOL", "SERVER_SOFTWARE", "REMOTE_ADDR",
        "HTTP_HOST", "HTTP_USER_AGENT", "HTTP_ACCEPT",
    ]
    for key in important_keys:
        if key in env_get:
            print(f"  {key:<28} = {env_get[key]}")

    # -----------------------------------------------------------------------
    # 3. CGI gateway processes the GET request
    # -----------------------------------------------------------------------
    section("3. CGI GATEWAY: GET ?name=Alice&color=%230077cc")
    http_resp_bytes, _ = cgi_gateway(get_raw)
    resp_text = http_resp_bytes.decode("latin-1")
    resp_lines = resp_text.split("\r\n")
    print("  [HTTP response head]")
    for line in resp_lines[:8]:
        print(f"  {line}")
    body_start = http_resp_bytes.find(b"\r\n\r\n") + 4
    body_preview = http_resp_bytes[body_start : body_start + 200].decode(
        "utf-8", errors="replace"
    )
    print("\n  [Body preview — first 200 chars]")
    for ln in body_preview.splitlines():
        print(f"  {ln}")
    print(f"\n  Total response size: {len(http_resp_bytes)} bytes")

    assert b"Hello, Alice!" in http_resp_bytes, "Expected 'Hello, Alice!' in GET response"
    print("  VERIFY: 'Hello, Alice!' found in response body  [OK]")

    # -----------------------------------------------------------------------
    # 4. POST request (form submission)
    # -----------------------------------------------------------------------
    section("4. CGI GATEWAY: POST /cgi-bin/app.py  (form submission)")
    post_body_str = "name=Bob&color=%23cc4400"
    post_raw = (
        "POST /cgi-bin/app.py HTTP/1.1\r\n"
        "Host: localhost:8080\r\n"
        "User-Agent: Demo/1.0\r\n"
        "Content-Type: application/x-www-form-urlencoded\r\n"
        f"Content-Length: {len(post_body_str)}\r\n"
        "Connection: keep-alive\r\n"
        "\r\n"
        f"{post_body_str}"
    )
    req_post = parse_http_request(post_raw)
    env_post = build_cgi_env(req_post)
    print(f"  REQUEST_METHOD   = {env_post['REQUEST_METHOD']}")
    print(f"  CONTENT_TYPE     = {env_post.get('CONTENT_TYPE', '(not set)')}")
    print(f"  CONTENT_LENGTH   = {env_post.get('CONTENT_LENGTH', '0')}")
    print(f"  stdin (POST body): {req_post.body!r}")

    http_resp_post, _ = cgi_gateway(post_raw)
    post_lines = http_resp_post.decode("latin-1").split("\r\n")
    print(f"\n  [HTTP response status]  {post_lines[0]}")
    for line in post_lines[1:6]:
        print(f"  {line}")

    assert b"Hello, Bob!" in http_resp_post, "Expected 'Hello, Bob!' in POST response"
    print("  VERIFY: 'Hello, Bob!' found in POST response body  [OK]")

    # -----------------------------------------------------------------------
    # 5. QUERY_STRING parsing (RFC 3986 §3.4)
    # -----------------------------------------------------------------------
    section("5. QUERY STRING DECODING  (urllib.parse.parse_qs)")
    samples = [
        ("name=Alice&color=%230077cc",   "percent-encoded color"),
        ("q=hello+world&lang=en&page=2", "plus-encoded spaces"),
        ("a=1&a=2&a=3",                  "multi-value parameter"),
        ("",                              "empty query string"),
    ]
    for qs, label in samples:
        parsed = urllib.parse.parse_qs(qs)
        print(f"  '{qs}'  ({label})")
        print(f"    -> {parsed}")

    # -----------------------------------------------------------------------
    # 6. CGI per-request fork overhead model
    # -----------------------------------------------------------------------
    section("6. CGI FORK OVERHEAD MODEL  (CGI/1.1 vs FastCGI vs WSGI)")
    print("  CGI/1.1 (RFC 3875) lifecycle per request:")
    steps = [
        ("1. Server receives HTTP request",                       ""),
        ("2. Server fork()s a new OS process",                    "~1-5 ms"),
        ("3. Server exec()s the CGI script (Python interpreter)", "~10-20 ms"),
        ("4. Request data copied via env vars + stdin pipe",      ""),
        ("5. Script generates response + writes to stdout",       ""),
        ("6. Server reads stdout -> sends HTTP response",         ""),
        ("7. Process exits  (memory freed)",                      ""),
    ]
    for step, cost in steps:
        suffix = f"  [{cost}]" if cost else ""
        print(f"    {step}{suffix}")
    print()
    fork_exec_ms = 15
    print(f"  Estimated fork+exec overhead: ~{fork_exec_ms} ms per request")
    print()
    print(f"  {'Req/s':>8}  {'Overhead':>12}  {'% of 1-second budget':>22}")
    print(f"  {'-'*8}  {'-'*12}  {'-'*22}")
    for rps in (1, 10, 50, 100, 500):
        overhead_ms = rps * fork_exec_ms
        pct = overhead_ms / 10.0
        flag = "  <-- unsustainable" if pct >= 100 else ""
        print(f"  {rps:>8}  {overhead_ms:>9} ms  {pct:>20.0f}%{flag}")
    print()
    print("  Solutions:")
    print("    FastCGI : persistent process pool; socket protocol; no fork per req")
    print("    WSGI    : Python callable in same process as server; no exec at all")
    print("    ASGI    : async WSGI; supports WebSockets and HTTP/2 streaming")

    # -----------------------------------------------------------------------
    # 7. Server-side vs client-side rendering
    # -----------------------------------------------------------------------
    section("7. SSR vs CSR RENDERING MODEL COMPARISON")
    print()
    print("  SERVER-SIDE RENDERING (SSR)  — CGI, PHP, JSP, ASP.NET, Django:")
    print("    Client -> [GET /products?cat=books] -> Server")
    print("    Server: query DB + render HTML template")
    print("    Server -> [200 OK, complete HTML page] -> Client")
    print("    Client: parse + render (no JS required)")
    print()
    print("  CLIENT-SIDE RENDERING (CSR)  — React, Vue, Angular:")
    print("    Client -> [GET /products?cat=books] -> Server")
    print("    Server -> [200 OK, skeleton HTML + bundle.js] -> Client")
    print("    Client: run bundle.js")
    print("    Client -> [GET /api/products?cat=books] -> JSON API server")
    print("    Server -> [200 OK, {products: [...]}] -> Client")
    print("    Client: JS renders DOM from JSON data")
    print()
    rows = [
        ("Complete HTML on first response",    "Rich interactivity without page reloads"),
        ("Works without JavaScript",           "Server sends JSON, not markup"),
        ("Better SEO (crawlers see HTML)",     "Decouples frontend from backend codebase"),
        ("Simpler full-page caching",          "App-like UX after initial load"),
        ("Lower time-to-first-byte risk",      "No server HTML rendering CPU cost"),
    ]
    print(f"  {'SSR advantage':<42} {'CSR advantage'}")
    print(f"  {'-'*42} {'-'*42}")
    for ssr_adv, csr_adv in rows:
        print(f"  {ssr_adv:<42} {csr_adv}")

    # -----------------------------------------------------------------------
    # 8. CSR: JSON API response
    # -----------------------------------------------------------------------
    section("8. CSR: JSON API RESPONSE PAYLOAD")
    print("  GET /api/search?q=computer+networks  HTTP/1.1")
    print("  < 200 OK  Content-Type: application/json")
    print()
    api_resp = client_side_api_response("computer networks")
    for line in json.dumps(api_resp, indent=4).splitlines():
        print(f"  {line}")
    print()
    print("  This JSON is what the server sends.  JavaScript in the browser")
    print("  fetches it, iterates 'results', and inserts <li> elements into")
    print("  the DOM.  No HTML was generated on the server.")

    # -----------------------------------------------------------------------
    # 9. Technology spectrum
    # -----------------------------------------------------------------------
    section("9. TECHNOLOGY SPECTRUM  (SSR -> Hybrid -> CSR)")
    tech_rows = [
        ("CGI/1.1 (RFC 3875)", "SSR",    "1993", "fork per request; any language"),
        ("PHP/FPM",             "SSR",    "1994", "FastCGI pool; embedded in nginx"),
        ("JSP (Java)",          "SSR",    "1999", "compiled to Servlet; JVM persistent"),
        ("ASP.NET",             "SSR",    "2002", "IIS/.NET; compiled"),
        ("Django / Rails",      "SSR",    "2000s","WSGI/Rack; MVC; template engine"),
        ("Ajax + jQuery",       "Hybrid", "2006", "partial DOM updates; server still SSR"),
        ("React / Vue / Angular","CSR",   "2010s","SPA; virtual DOM; JSON APIs"),
        ("Next.js / Nuxt",      "Hybrid", "2020s","SSR+CSR hydration; streaming RSC"),
    ]
    print(f"  {'Technology':<28}  {'Model':<8}  {'Year':<6}  Notes")
    print(f"  {'-'*28}  {'-'*8}  {'-'*6}  {'-'*40}")
    for tech, model, year, notes in tech_rows:
        print(f"  {tech:<28}  {model:<8}  {year:<6}  {notes}")

    print("\n" + "=" * 64)
    print("  All CGI and rendering model simulations completed.")
    print("=" * 64)


if __name__ == "__main__":
    main()
