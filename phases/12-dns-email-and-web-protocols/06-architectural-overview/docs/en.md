# Web Architectural Overview

> The Web is an **architectural framework** for accessing linked content spread across millions of machines. It started in **1989** at **CERN** when **Tim Berners-Lee** proposed a web of linked documents to help large physics collaborations; the first text-based prototype ran 18 months later and the graphical **Mosaic** browser from the University of Illinois appeared in February 1993. The fundamental model is **pages** connected by **hyperlinks**, fetched by a **browser** over **HTTP on TCP port 80**, rendered using **HTML**, **CSS**, and increasingly JavaScript. Pages are addressed by **URLs** of the form `scheme://host/path` (RFC 3986). HTML's role as the lingua franca plus the rise of high-bandwidth access produced an exponential growth from a handful of sites in 1993 to billions of pages today. The **W3C**, founded in 1994 by CERN and MIT, owns the standards. Browsers extend with **plug-ins** (Flash, PDF) and **helper applications** (Word, Photoshop) keyed to **MIME types** (`text/html`, `application/pdf`, etc.). Web servers became multithreaded front-end + k processing modules sharing an in-memory cache. **Cookies** (RFC 2109) — small named strings up to 4 KB stored client-side — give servers session memory across stateless HTTP requests.

**Type:** Build
**Languages:** HTTP, HTML, Python (URL parser, cookie parser)
**Prerequisites:** Phase 6 (TCP), Phase 12 Lesson 02 (DNS)
**Time:** ~120 minutes

## Learning Objectives

- Diagram the Web's three-component model (browser, server, network) and trace a click from URL parsing to rendered page.
- Decompose a URL into scheme, authority, path, query, fragment per RFC 3986.
- Distinguish static from dynamic pages, and explain when each is appropriate.
- Map a real URL like `http://www.cs.washington.edu/index.html` to the nine-step fetch sequence in the textbook.
- Articulate the role of plug-ins vs. helper applications and how MIME types drive the browser's dispatch.

## The Problem

A user clicks a link in Safari. The browser must: parse a URL, look up the host via DNS, open a TCP connection, send an HTTP GET, receive the response body, parse the HTML, follow it to dozens of embedded resources, render the page, and remember who the user is for next time. The Web is a stack of standards stitched together by browser engineers, and every step has its own failure mode. You need to understand the architecture — what runs where, who talks to whom, what stays where — to debug any real Web problem.

## The Concept

### The nine-step click sequence

The textbook walks through what happens when a user clicks a hyperlink that resolves to `http://www.cs.washington.edu/index.html`:

```text
1. Browser determines the URL (by seeing what was selected).
2. Browser asks DNS for the IP address of www.cs.washington.edu.
3. DNS replies with 128.208.3.88.
4. Browser makes a TCP connection to 128.208.3.88 on port 80.
5. Browser sends an HTTP request asking for the page /index.html.
6. The www.cs.washington.edu server sends the page as an HTTP response.
7. If the page includes URLs needed for display, the browser fetches them
   using the same process (multiple embedded images, video, scripts).
8. The browser displays /index.html.
9. The TCP connections are released if no other requests follow.
```

Each step can fail. Step 2 (DNS) shows up as "server not found." Step 4 (TCP) shows as "connection refused" or a long stall. Step 5 (HTTP) shows as 4xx/5xx codes. Step 7 (subresources) is the most expensive — a typical modern page triggers 40+ subresource fetches.

### The three-component architecture

The textbook's Figure 7-18 distils the Web into three actors:

| Component | Where it runs | Examples | Responsibility |
|-----------|---------------|----------|----------------|
| **Browser** (Web client) | User's machine | Chrome, Firefox, Safari, Edge, curl | Fetch, parse, render, execute scripts |
| **Web server** | Datacenter | Apache, nginx, IIS, Caddy, lighttpd | Resolve path, access control, fetch or generate page, log |
| **Network** | Between them | Routers, switches, CDNs | Reliable byte stream (TCP), name resolution (DNS) |

The browser is more than a renderer — it is a runtime for HTML, CSS, JavaScript, plug-ins, and increasingly WebAssembly. The Web server is more than a file server — it executes server-side scripts, queries databases, talks to upstream APIs, and pushes to CDNs.

### URLs — the addressing language

A **URL** (Uniform Resource Locator, RFC 3986) names a resource and tells you how to fetch it. General form:

```text
scheme://authority/path?query#fragment
```

| Component | Example | Function |
|-----------|---------|----------|
| `scheme` | `http`, `https`, `ftp`, `mailto`, `file`, `rtsp`, `sip`, `about` | Protocol to use |
| `authority` | `www.example.com:8080` | DNS name + optional port |
| `path` | `/index.html` | Hierarchical path on server |
| `query` | `?q=cat&page=2` | Optional parameters |
| `fragment` | `#section-3` | Client-side anchor |

URL schemes in common use (Figure 7-19):

| Scheme | Used for | Example |
|--------|----------|---------|
| `http` | HTML pages | `http://www.ee.uwa.edu/~rob/` |
| `https` | HTTP over TLS | `https://www.bank.com/accounts/` |
| `ftp` | File transfer | `ftp://ftp.cs.vu.nl/pub/minix/README` |
| `file` | Local file | `file:///usr/suzanne/prog.c` |
| `mailto` | Compose email | `mailto:JohnUser@acm.org` |
| `rtsp` | Streaming media | `rtsp://youtube.com/montypython.mpg` |
| `sip` | VoIP calls | `sip:eve@adversary.com` |
| `about` | Browser internals | `about:plugins` |

URLs only tell you **how to locate** a resource. They do not tell you **what** the resource is named. For that, you want a **URN** (Uniform Resource Name). The umbrella term for both is **URI** (Uniform Resource Identifier).

### MIME types and browser dispatch

Every response from a Web server carries a `Content-Type` header naming the MIME type. The browser uses it to decide how to render or hand off the body:

```
Content-Type: text/html; charset=utf-8     → render inline as HTML
Content-Type: image/png                    → decode and display image
Content-Type: application/pdf              → hand off to PDF plug-in
Content-Type: application/octet-stream      → prompt to save file
Content-Type: text/css                     → parse and apply as stylesheet
Content-Type: application/javascript        → execute as JavaScript
```

Two extension mechanisms handle types the browser doesn't know natively:

- **Plug-ins** (in-process modules): PDF, Flash, video codecs. They run inside the browser process and can modify the displayed page.
- **Helper applications** (out-of-process programs): Word, PowerPoint, Photoshop. The browser saves the content to a scratch file and launches the helper.

When multiple plug-ins claim the same MIME type, the last one installed wins. Installing a new video player can quietly hijack `.mp4` playback for every other site.

### Server-side architecture

A modern Web server is multithreaded:

```text
        +--------+
        |  TCP   | (listening socket, port 80)
        | accept |
        +----+---+
             |
             v
        +--------+      +-------------+      +--------+
        | Front  | ---> | Processing  | ---> |  Disk  |
        |  end   |      |  module k   |      +--------+
        +--------+      +------+------+
                              |
                              v
                        +-----+-----+      +---------+
                        |   Cache   | <--> |  Logs   |
                        +-----------+      +---------+
```

The front end accepts incoming TCP connections and hands each request to a free processing module. Each processing module then runs a sequence of steps:

1. **Resolve the page name** — map `/~ast/` to `/home/ast/public_html/index.html`; expand `http://www.cs.vu.nl/` to the directory's default file.
2. **Access control** — check `.htaccess` rules or HTTP auth.
3. **Cache check** — see if the page is already in memory.
4. **Fetch or generate** — read from disk or run a CGI script / PHP / Python handler.
5. **Determine MIME type** — by extension, configuration, or content sniffing.
6. **Send response** — write headers, then body, with persistent connection handling.
7. **Log** — record the request for analytics and abuse response.

### Static vs dynamic pages

| Property | Static page | Dynamic page |
|----------|-------------|--------------|
| Source | A file on disk | Generated on each request by a program |
| Same per request? | Yes | Often no (personalisation, A/B testing) |
| Cacheable | Yes, indefinitely | Usually with caveats |
| Hosting cost | Cheap (CDN-friendly) | Higher (CPU + DB per request) |
| When to use | Marketing pages, docs, blog posts | Dashboards, search results, account pages |

A page that embeds video is still **static** — the HTML is fixed, even though the embedded resource is large. The dynamic/static distinction is about the HTML returned, not the assets it references.

### Cookies — stateless becomes stateful

HTTP is intrinsically stateless: each request is independent. To support logins, shopping carts, and personalisation, **Netscape invented cookies in 1994**, later standardised in **RFC 2109** and updated by RFC 2965 (mostly rejected) and RFC 6265 (current).

A cookie is a small named string (max 4 KB) attached by the server with `Set-Cookie:` and returned by the client with `Cookie:`. Five fields:

| Field | Example | Meaning |
|-------|---------|---------|
| Domain | `toms-casino.com` | Where the cookie came from (and where it may be sent) |
| Path | `/` | Which URLs on the server see the cookie |
| Content | `CustomerID=297793521` | The actual data, in `name=value` form |
| Expires | `15-10-10 17:00` | When to discard; absent = session-only |
| Secure | `Yes` | Only return over HTTPS |

Two varieties:

- **Session cookies** — no Expires field; discarded when the browser exits.
- **Persistent cookies** — with Expires field; kept on disk until expiry.

A third distinction matters for privacy:

- **First-party cookie** — set by the domain the user is visiting. Functional.
- **Third-party cookie** — set by a different domain (an ad network, an analytics provider). Used to track users across sites. Blocked by most modern browsers by default.

### Plug-ins vs. helpers in detail

The textbook Figure 7-20 illustrates both:

- **Plug-in (a)**: runs as a child process or in-process module of the browser. Has a defined interface (allocate memory, display, get URL, status line). Examples: Flash (now deprecated), Java, PDF viewers in browsers, video codecs.
- **Helper application (b)**: a standalone program. The browser hands it a scratch file and lets it render. Examples: Microsoft Word, Photoshop, large IDEs.

Plug-ins are faster (in-process, direct DOM access) but riskier (any bug becomes a browser bug). Helpers are safer (isolated) but less responsive. The MIME type registry is the bridge — when a browser sees a type it does not handle natively, it consults its MIME-to-handler table.

## Build It

1. Run `python3 code/main.py` to parse URLs into components and inspect a sample `Set-Cookie` header.
2. Open the browser dev tools (Network tab), click a link, and observe the actual nine-step sequence plus the subresource fetches in step 7.
3. View cookies in your browser's settings; classify them as first-party vs third-party.
4. Inspect `assets/web-architecture.svg` for the three-component diagram.

## Use It

| Task | Tool | What Good Looks Like |
|------|------|----------------------|
| Parse a URL | Python `urllib.parse.urlparse` | scheme, netloc, path, query, fragment |
| Trace a click | Browser Network tab | DNS, TCP, TLS, Request, Response visible |
| Inspect cookies | Browser dev tools Application tab | Domain, Path, Expires, HttpOnly, Secure |
| Check MIME types | `curl -I https://example.com` | `Content-Type:` header |
| Compare static vs dynamic | `curl -v` vs `curl -b cookies.txt -v` | Different bodies for different cookies |

## Ship It

Under `outputs/`, build a URL/cookie parser that emits a JSON document listing all components, plus a one-page critique of a real website's cookie use (which are essential, which are trackers). Start with [`outputs/prompt-web-architectural-overview.md`](../outputs/prompt-web-architectural-overview.md).

## Exercises

1. Decompose `https://www.example.com:8443/path/to/page?q=hello#section-2` into scheme, authority, path, query, fragment.
2. The textbook says step 7 fetches "multiple embedded images, an embedded video, and a script." How does the browser know to fetch them and how many simultaneous TCP connections does it open?
3. A page is served with `Content-Type: text/plain` but contains HTML tags. Why does the browser show the tags as text instead of rendering?
4. The server logs `200 412 GET /index.html Mozilla/5.0`. Decode each field.
5. Why are cookies limited to 4 KB and at most 20 per domain? What would break if these limits did not exist?
6. The browser stores a cookie with `Domain=.example.com`. Which other hostnames will receive that cookie on subsequent requests?

## Key Terms

| Term | Plain English | Technical meaning |
|------|---------------|-------------------|
| Web | "the World Wide Web" | Linked document system over HTTP |
| Browser | "the Web program" | Fetches, renders, executes pages |
| URL | "Web address" | RFC 3986 universal resource locator |
| URN | "permanent name" | URI that names without locating |
| URI | "identifier umbrella" | URL or URN |
| MIME type | "what kind of body" | RFC 6838 `type/subtype` label |
| Plug-in | "browser extension" | In-process module that renders one MIME type |
| Helper application | "external viewer" | Out-of-process program for one MIME type |
| HTTP | "the Web protocol" | RFC 2616/7230-7235 request-response |
| Cookie | "client-side memory" | RFC 6265 named string set by server |
| Static page | "fixed content" | Same bytes every request |
| Dynamic page | "generated per request" | Bytes depend on user, query, DB |

## Further Reading

- RFC 3986 — Uniform Resource Identifier (URI): Generic Syntax
- RFC 6265 — HTTP State Management Mechanism (Cookies)
- RFC 6838 — Media Type Specifications and Registration Procedures
- RFC 2616 / 7230-7235 — HTTP/1.1
- Berners-Lee, *Information Management: A Proposal*, CERN, 1989
- Andreessen, *Mosaic browser release notes*, NCSA, 1993
- W3C standards track: https://www.w3.org/standards/
- IANA Media Type Registry
- Fielding, *Architectural Styles and the Design of Network-based Software Architectures* (REST dissertation), 2000
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 7, Section 7.3.1
