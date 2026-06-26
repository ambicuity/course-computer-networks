# CGI, Server-Side, and Client-Side Web Apps

> CGI (RFC 3875) made the web dynamic by letting a web server spawn a separate process for each request, pass all request data through environment variables and stdin, and read the dynamically generated response from that process's stdout — a model so simple it worked in any language, and so expensive it drove the invention of everything that came after it.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 12 lessons on HTTP methods, headers, cookies, and caching
**Time:** ~75 minutes

## Learning Objectives

- Describe the CGI/1.1 request-handling model: fork, exec, env vars, stdin, stdout.
- Name and explain the mandatory CGI environment variables (REQUEST_METHOD, QUERY_STRING, CONTENT_LENGTH, PATH_INFO, SERVER_NAME, GATEWAY_INTERFACE, etc.).
- Trace a GET and POST request through the CGI gateway and explain exactly which bytes flow where.
- Distinguish server-side rendering (SSR) from client-side rendering (CSR) and state at least three trade-offs for each.
- Explain why FastCGI, WSGI, and modern frameworks exist as alternatives to CGI/1.1.
- Place PHP, JSP, ASP.NET, Django, React, and Next.js on the SSR/CSR/hybrid spectrum.

## The Problem

In 1993 the first web servers (NCSA HTTPd, CERN httpd) could only serve static files — every response was a document that existed on disk before the request arrived. That was fine for hypertext papers, but terrible for anything that needed to change: a search engine, a form that updated a database, a page that showed today's weather. The web needed dynamic content.

The obvious solution — hard-code the dynamic logic into the web server itself — was unacceptable: it coupled the application language to the server binary, required a server recompile for every new application, and made security bugs in one application dangerous to the whole server. What was needed was a standard contract between the server (which handles TCP, TLS, and HTTP parsing) and user code (which knows what the response should say).

CGI solved this. The server and the application agree on a clean interface: the server forks a new process, communicates the request details via a well-defined set of environment variables and via the process's standard input stream, and reads the dynamic response from the process's standard output stream. The application can be a shell script, a Perl script, a C binary, a Python program — it does not matter, because the interface is purely OS primitives (fork, exec, pipes, environment). Once the script writes its response and exits, the server sends the output to the client and the process disappears.

This model was so approachable that the web's first wave of interactivity — forms, hit counters, guest books, early e-commerce — was built almost entirely on CGI scripts. Its simplicity is also its main weakness: spawning a new OS process for every HTTP request is expensive. At ten requests per second that is acceptable; at hundreds per second the fork-exec overhead dominates.

## The Concept

### CGI/1.1 and RFC 3875

The Common Gateway Interface was first documented in 1993, standardized as CGI/1.1, and codified in RFC 3875 (2004). It defines:

1. **How the server communicates the request to the script** — via environment variables and, for POST/PUT, via stdin.
2. **How the script communicates the response to the server** — by writing HTTP response headers followed by the body to stdout.
3. **The lifecycle** — the server forks, execs, waits; the script runs, writes, exits.

The server is called the **gateway** in RFC 3875 terminology; the script is called the **CGI script** or **resource**. Together they form the gateway-resource pair.

### CGI Environment Variables (RFC 3875 §4.1)

Every CGI script sees a set of environment variables populated by the server before exec():

| Variable | RFC 3875 §4.1 | What it contains |
|---|---|---|
| `GATEWAY_INTERFACE` | §4.1.4 | `CGI/1.1` — the version the server implements |
| `REQUEST_METHOD` | §4.1.12 | `GET`, `POST`, `PUT`, `DELETE`, `HEAD`, etc. |
| `SCRIPT_NAME` | §4.1.13 | Logical path of the script, e.g., `/cgi-bin/app.py` |
| `PATH_INFO` | §4.1.9 | Extra path info after the script name, e.g., `/users/42` |
| `QUERY_STRING` | §4.1.7 | Everything after `?` in the URL, URL-encoded |
| `SERVER_NAME` | §4.1.14 | Hostname from the HTTP Host header or configured name |
| `SERVER_PORT` | §4.1.15 | TCP port the server is listening on |
| `SERVER_PROTOCOL` | §4.1.16 | `HTTP/1.0` or `HTTP/1.1` |
| `SERVER_SOFTWARE` | §4.1.17 | Server name and version, e.g., `Apache/2.4` |
| `REMOTE_ADDR` | §4.1.8 | Client's IP address |
| `REMOTE_HOST` | §4.1.9 | Client's hostname (if DNS reverse lookup done) |
| `CONTENT_TYPE` | §4.1.3 | MIME type of the request body (POST only) |
| `CONTENT_LENGTH` | §4.1.2 | Byte length of the request body (POST only) |
| `AUTH_TYPE` | §4.1.1 | Authentication scheme if server did authentication |
| `REMOTE_USER` | §4.1.11 | Authenticated username if AUTH_TYPE is set |

Every HTTP request header is also exposed as an environment variable prefixed with `HTTP_`, with header names uppercased and hyphens replaced by underscores. Examples:

| HTTP header | CGI variable |
|---|---|
| `Host:` | `HTTP_HOST` |
| `User-Agent:` | `HTTP_USER_AGENT` |
| `Accept:` | `HTTP_ACCEPT` |
| `Cookie:` | `HTTP_COOKIE` |
| `Referer:` | `HTTP_REFERER` |
| `Accept-Encoding:` | `HTTP_ACCEPT_ENCODING` |

### The CGI Request-Response Flow

**GET request with query parameters:**

```
Client                    Server (Gateway)              CGI Script
  |                            |                              |
  |-- GET /cgi-bin/app?name=X  |                              |
  |   Host: example.com        |                              |
  |                            |-- fork() + exec(app.py) ---> |
  |                            |   env: REQUEST_METHOD=GET    |
  |                            |        QUERY_STRING=name=X   |
  |                            |        SERVER_NAME=example.. |
  |                            |                              |-- read env vars
  |                            |                              |-- parse name=X
  |                            |                              |-- generate HTML
  |                            |<-- stdout: Content-Type:...  |
  |                            |           (blank line)       |-- exit(0)
  |                            |           <html>...</html>   |
  |<-- HTTP/1.1 200 OK --------|                              |
  |    Content-Type: text/html |                              |
  |    <html>...</html>        |                              |
```

**POST request with form body:**

```
Client                    Server (Gateway)              CGI Script
  |                            |                              |
  |-- POST /cgi-bin/app ------>|                              |
  |   Content-Type: applic...  |                              |
  |   Content-Length: 22       |                              |
  |   name=Bob&color=red       |                              |
  |                            |-- fork() + exec(app.py) ---> |
  |                            |   env: REQUEST_METHOD=POST   |
  |                            |        CONTENT_TYPE=applic.. |
  |                            |        CONTENT_LENGTH=22     |
  |                            |   stdin: name=Bob&color=red  |
  |                            |                              |-- os.environ
  |                            |                              |-- sys.stdin.read(22)
  |                            |                              |-- parse POST body
  |                            |                              |-- generate HTML
  |                            |<-- stdout: Content-Type...   |-- exit(0)
  |<-- HTTP/1.1 200 OK --------|                              |
```

The key point: for GET the data travels in `QUERY_STRING`; for POST the data travels in stdin and the script must read exactly `CONTENT_LENGTH` bytes from it.

### CGI Script Output Format

A CGI script writes to stdout. The output must begin with CGI response headers (not a full HTTP status line — that is the server's job), followed by a blank line, followed by the body:

```
Content-Type: text/html; charset=utf-8\r\n
X-My-Header: value\r\n
\r\n
<!DOCTYPE html>
<html>...</html>
```

Optionally, a script can set the status code using the `Status:` CGI header:

```
Status: 302 Found\r\n
Location: /new-path\r\n
Content-Type: text/html\r\n
\r\n
Redirecting...
```

The server reads these headers, discards the `Status:` line (using its value to construct the HTTP status line), and forwards the remaining headers and body to the client.

### Query String Encoding (RFC 3986 §3.4)

The query string is URL-encoded (percent-encoded): spaces become `+` or `%20`, special characters become `%XX`. A script must decode the query string before using it. In Python: `urllib.parse.parse_qs(os.environ["QUERY_STRING"])`. For POST bodies of type `application/x-www-form-urlencoded`, the same encoding applies but arrives on stdin.

### CGI Performance Problem and Solutions

Each HTTP request causes the server to:
1. Call `fork()` to create a child process (~1–5 ms on Linux, more on memory-heavy servers)
2. Call `exec()` to replace the child with the script interpreter (~10–20 ms to load Python/Perl)
3. Wait for the script to finish and read its stdout

At low request rates (< 10 req/s) this is fine. At 100 req/s, the fork overhead alone is 100 × 15 ms = 1,500 ms of CPU per second, leaving little room for actual computation. At 500 req/s, CGI cannot keep up at all.

**FastCGI** (1996) solves this: instead of forking per request, the server maintains a pool of long-running processes that communicate over a socket using a multiplexed binary protocol. No fork, no exec, no interpreter startup. The application pool is created once and reused.

**WSGI** (PEP 3333, Python) goes further: the web server calls a Python callable (a function or object) directly in the same process (or via an adapter). No OS process boundary at all. Django, Flask, and FastAPI all expose a WSGI or ASGI interface. Apache mod_wsgi, gunicorn, and uWSGI are the common WSGI servers.

Equivalent standards in other ecosystems: **PSGI** (Perl), **Rack** (Ruby), **JSGI** (JavaScript/Node), **Jakarta Servlet API** (Java/JSP).

### Server-Side Rendering (SSR)

In SSR, the server (CGI script, PHP file, JSP page, or Django view) generates a complete HTML document and sends it to the browser. The browser receives finished markup, renders it, and displays the page.

**How it works:**
1. Browser requests `/products?category=books`
2. Server queries the database for books
3. Server renders an HTML template filled with book data
4. Server sends the complete HTML to the browser
5. Browser renders the page (no JavaScript needed)

**Technology examples and how they implement SSR:**
- **PHP**: PHP code embedded in HTML files with `<?php ?>` tags; Apache or nginx runs PHP-FPM (FastCGI pool) per request
- **JSP (JavaServer Pages)**: HTML with `<% %>` scriptlets, compiled to Java Servlet classes, run in Tomcat/Jetty
- **ASP / ASP.NET**: Microsoft's equivalent; .aspx pages compiled to .NET assemblies, run in IIS
- **Django (Python)**: Views return `HttpResponse`, templates render context dicts to HTML via the Django template engine
- **Rails (Ruby)**: ERB templates rendered by Action Controller, served via Rack

**SSR trade-offs:**

| Advantage | Disadvantage |
|---|---|
| Complete HTML on first response (fast FCP) | Full page reload for every navigation |
| Works without JavaScript | Higher server CPU for HTML generation |
| Search engine crawlers see full content | Harder to build rich interactive UIs |
| Simple caching (cache the HTML page) | Server must be scaled for rendering load |
| TTFB includes all data | Latency for every action (network round-trip) |

### Client-Side Rendering (CSR)

In CSR, the server sends a minimal HTML skeleton (often just a `<div id="app"></div>` and a `<script>` tag). JavaScript runs in the browser, calls JSON APIs to fetch data, and builds the DOM dynamically.

**How it works:**
1. Browser requests `/products?category=books`
2. Server sends `index.html` (skeleton) + `bundle.js`
3. Browser downloads and runs `bundle.js`
4. JavaScript calls `GET /api/products?category=books` (JSON)
5. Server returns `{"products": [...]}`
6. JavaScript renders the DOM from the JSON data

**Technology examples:**
- **XMLHttpRequest (XHR) / AJAX** (2005): Made asynchronous fetches possible; jQuery wrapped it in `$.ajax()`
- **React** (2013): Virtual DOM, component model, hooks; JSX compiles to `React.createElement()` calls
- **Vue** (2014): Progressive framework; reactive data binding via Proxy
- **Angular** (2016): Full MVC framework; TypeScript-first; dependency injection
- All three typically call a REST or GraphQL API and render the response to DOM

**CSR trade-offs:**

| Advantage | Disadvantage |
|---|---|
| Rich interactivity without page reloads | Slow First Contentful Paint (JS download + parse + execute) |
| Server sends data (JSON), not markup | Poor SEO (crawler sees skeleton HTML, not content) |
| App-like UX after initial load | Broken without JavaScript |
| Separates backend from frontend codebases | More complex debugging (client + server logs) |
| Reduced server load (no HTML rendering) | JS bundle size management is ongoing work |

### Hybrid Rendering

Modern meta-frameworks blend SSR and CSR:

- **Next.js** (React): Pages can be server-rendered per request (SSR), statically generated at build time (SSG), or streamed with React Server Components. The initial page is SSR; subsequent navigations use client-side routing.
- **Nuxt** (Vue): Same model as Next.js for Vue.
- **SvelteKit** (Svelte): Server-side rendering by default; hydration adds interactivity.

The pattern is: **render the initial page on the server** (good for SEO and FCP), then **hydrate** it in the browser (add event listeners), and use client-side navigation for subsequent pages (fast, no full reload).

### The Technology Spectrum

| Technology | Model | Year | Notes |
|---|---|---|---|
| CGI/1.1 (RFC 3875) | SSR | 1993 | fork per request; any language |
| PHP | SSR | 1994 | FPM pool; embedded in Apache/nginx |
| ASP | SSR | 1996 | IIS; VBScript/JScript |
| JSP (Java) | SSR | 1999 | compiled to Servlet; JVM persistent |
| ASP.NET | SSR | 2002 | IIS/.NET; compiled |
| Django/Rails | SSR | 2000s | WSGI/Rack; MVC framework |
| Ajax + jQuery | CSR (partial) | 2006 | partial DOM updates; full HTML from server |
| React/Vue/Angular | CSR | 2010s | SPA; virtual DOM; JSON APIs |
| Next.js/Nuxt/SvelteKit | Hybrid | 2020s | SSR+CSR; hydration; streaming |

## Build It

### Step 1 — Run the included simulator

```bash
cd phases/12-dns-email-and-web-protocols/25-cgi-server-side-and-client-side-web-apps
python3 code/main.py
```

The simulator:
- Parses a raw HTTP GET and POST request
- Builds the RFC 3875 CGI environment variable set
- Calls a CGI "script" function (simulating exec()) that reads env vars and stdin, generates HTML
- Prints the full HTTP response the gateway would return to the client
- Shows the fork overhead model and SSR vs CSR comparison

### Step 2 — Understand the CGI env var builder

The function `build_cgi_env(req)` in `code/main.py` maps each HTTP request field to the correct RFC 3875 §4.1 environment variable. Read through it and verify:

- `REQUEST_METHOD` comes from the HTTP method
- `QUERY_STRING` comes from the URL after `?` (before URL decoding)
- `CONTENT_LENGTH` is set only for POST/PUT and equals the body length
- `HTTP_USER_AGENT` is set from the `User-Agent:` request header

### Step 3 — Understand the CGI script function

`cgi_script(env, stdin)` is the script the server would `exec()`. It:
1. Reads `os.environ` equivalent (the `env` dict)
2. For GET: parses `QUERY_STRING` with `urllib.parse.parse_qs`
3. For POST: reads `stdin[:CONTENT_LENGTH]` and parses the URL-encoded form body
4. Generates a dynamic HTML response with the parsed data embedded
5. Writes `Content-Type: ...`, other headers, blank line, body to stdout (returned as `bytes`)

### Step 4 — Write your own CGI script (optional)

Create a file `code/hello_cgi.py`:

```python
#!/usr/bin/env python3
import os
import urllib.parse

qs = os.environ.get("QUERY_STRING", "")
params = urllib.parse.parse_qs(qs)
name = params.get("name", ["World"])[0]

print("Content-Type: text/html; charset=utf-8")
print()  # blank line — required!
print(f"<html><body><h1>Hello, {name}!</h1></body></html>")
```

Test it locally by setting the env var yourself:

```bash
REQUEST_METHOD=GET QUERY_STRING="name=Alice" python3 code/hello_cgi.py
```

You should see the CGI response headers printed to stdout.

### Step 5 — Serve it with Python's built-in CGI server

Python's `http.server` module ships a CGI server:

```bash
mkdir -p /tmp/cgi_demo/cgi-bin
cp code/hello_cgi.py /tmp/cgi_demo/cgi-bin/hello.py
chmod +x /tmp/cgi_demo/cgi-bin/hello.py
cd /tmp/cgi_demo
python3 -m http.server --cgi 8080
```

Then in another terminal:

```bash
curl "http://localhost:8080/cgi-bin/hello.py?name=Alice"
```

Observe the Content-Type header and the HTML body with the name substituted.

### Step 6 — Test a POST form submission

```bash
curl -X POST \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "name=Bob&color=red" \
  "http://localhost:8080/cgi-bin/hello.py"
```

Modify `hello_cgi.py` to read POST data:

```python
import sys
method = os.environ.get("REQUEST_METHOD", "GET")
if method == "POST":
    length = int(os.environ.get("CONTENT_LENGTH", 0))
    body = sys.stdin.read(length)
    params = urllib.parse.parse_qs(body)
```

### Step 7 — Measure fork overhead

Time 10 sequential CGI requests:

```bash
time for i in $(seq 1 10); do
  curl -s "http://localhost:8080/cgi-bin/hello.py?name=test$i" > /dev/null
done
```

Each request spawns a new Python interpreter. Compare with the fork overhead model in `code/main.py` Section 6.

## Use It

| Capability | Our implementation | Real-world equivalent | Reference |
|---|---|---|---|
| HTTP request parser | `parse_http_request()` | `http.server.BaseHTTPRequestHandler` | RFC 7230 |
| CGI env builder | `build_cgi_env()` | Apache mod_cgi, nginx+cgi | RFC 3875 §4.1 |
| CGI script function | `cgi_script()` | Any CGI script in any language | RFC 3875 §6 |
| Query string parser | `urllib.parse.parse_qs()` | PHP `$_GET`, Django `request.GET` | RFC 3986 §3.4 |
| Form body parser | `urllib.parse.parse_qs(stdin)` | PHP `$_POST`, Django `request.POST` | RFC 1866 |
| Gateway wrapper | `cgi_gateway()` | Python `http.server --cgi` | RFC 3875 §4 |
| JSON API response | `client_side_api_response()` | Flask/FastAPI `jsonify()` | RFC 8259 |

## Ship It

Produce one reusable artifact under `outputs/`:

A runbook that proves you understand the CGI boundary: given a raw HTTP request on paper, derive all mandatory CGI environment variables by hand, identify whether QUERY_STRING or stdin carries the payload, and describe exactly what the server does with the CGI script's stdout.

Start from [`outputs/prompt-cgi-server-side-and-client-side-web-apps.md`](../outputs/prompt-cgi-server-side-and-client-side-web-apps.md).

## Exercises

1. Write a CGI script that reads `QUERY_STRING`, parses it, and returns a JSON response with `Content-Type: application/json`. Test it with `curl`.
2. Modify the CGI script to read a POST body of `application/json` (not form-encoded): read `CONTENT_LENGTH` bytes from stdin, parse with `json.loads()`, and echo back a transformed response.
3. Implement a hit counter: the CGI script reads a file `/tmp/count.txt`, increments the number, writes it back, and returns it as HTML. Observe what happens with concurrent requests.
4. Compare page load time: write an SSR endpoint that returns full HTML, and a CSR endpoint that returns JSON. Time both with `curl -w "%{time_total}"`. Add a 50 ms simulated DB query (`time.sleep(0.05)`) and observe how that affects the trade-off.
5. Add `Status: 302 Found\r\nLocation: /new-page\r\n` to your CGI script's output and use `curl -i` to confirm the server forwarded the redirect.
6. Run Python's `http.server --cgi` and capture the traffic with `tcpdump -w cgi.pcap port 8080`. Open in Wireshark and locate the fork boundary: the HTTP request arrives, then after a pause the HTTP response arrives. The pause is the fork+exec cost.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| CGI | "the old way to do dynamic pages" | RFC 3875: Common Gateway Interface — contract between web server and application process via env vars + stdin/stdout |
| GATEWAY_INTERFACE | "the CGI version header" | Env var set to `CGI/1.1`; tells the script which version of the spec it is running under |
| REQUEST_METHOD | "the HTTP method env var" | RFC 3875 §4.1.12: `GET`, `POST`, etc. — how the script knows which verb was used |
| QUERY_STRING | "the URL parameters" | RFC 3875 §4.1.7: the raw URL-encoded string after `?`, available to the script without further parsing by the gateway |
| CONTENT_LENGTH | "the POST body size" | RFC 3875 §4.1.2: byte count the script must read from stdin; reading more is undefined behavior |
| PATH_INFO | "extra path after the script" | RFC 3875 §4.1.9: e.g., `/users/42` in `/cgi-bin/app.py/users/42` |
| FastCGI | "CGI without the fork" | Protocol for long-running application processes that handle many requests over a socket, no exec per request |
| WSGI | "Python's CGI replacement" | PEP 3333: Python callable interface — `def app(environ, start_response)` — used by Django, Flask, FastAPI |
| SSR | "the server sends HTML" | Server-side rendering: complete HTML generated on the server and sent to the browser |
| CSR | "the browser builds the page" | Client-side rendering: minimal HTML + JS bundle; browser fetches JSON and builds the DOM |
| Hydration | "making SSR HTML interactive" | Process of attaching JavaScript event handlers to server-rendered HTML in the browser |
| SPA | "single-page app" | Single-Page Application: one HTML page, client-side routing, no full page reloads |
| AJAX | "background fetch" | Asynchronous JavaScript And XML: `XMLHttpRequest` (or `fetch()`) to update part of the DOM without reloading |

## Further Reading

- RFC 3875 — The Common Gateway Interface (CGI) Version 1.1
- RFC 3986 §3.4 — URI Query Component (query string syntax)
- RFC 1866 — HTML 2.0 (defines `application/x-www-form-urlencoded`)
- PEP 3333 — Python WSGI Interface Specification
- FastCGI Specification — https://fastcgi-archives.github.io/FastCGI_Specification.html
- Python docs: `http.server` — built-in CGI server for testing
- Python docs: `urllib.parse.parse_qs` — query string parsing
- WHATWG Fetch Standard — the browser `fetch()` API used in CSR
- Vercel blog: "What is SSR?" — practical Next.js SSR vs SSG vs CSR breakdown
- MDN: "Progressive Enhancement" — building pages that work without JavaScript
- Web Almanac (HTTP Archive, annual) — statistical breakdown of SSR vs CSR in production
