# Static Web Pages, Dynamic Web Pages, and Web Applications

> The earliest Web was **static**: HTML files sitting on disk, served as-is. **HTML** (HyperText Markup Language) is the lingua franca — a markup language with tags like `<h1>`, `<p>`, `<a href="...">`, `<img src="...">`, `<form>`, `<table>` that separate content from presentation. **CSS** (Cascading Style Sheets, RFC 2318 + later W3C) lets a single `.css` file set fonts, colors, spacing for thousands of pages. Modern static pages often embed **video**, **audio**, **SVG**, and **client-side scripts**. To handle forms, logins, and database-backed content, the Web shifted to **dynamic** generation: **CGI** (Common Gateway Interface, RFC 3875) spawns a process per request; **PHP** (PHP: Hypertext Preprocessor) embeds script in HTML and is parsed by an Apache module; **JSP** (JavaServer Pages) and **ASP.NET** (Active Server Pages) do the same in Java and C# respectively. **Client-side dynamic** uses **JavaScript** (unrelated to Java) running inside the browser, made responsive via the **DOM** (Document Object Model) and the **XMLHttpRequest** API. **AJAX** (Asynchronous JavaScript and XML) combines HTML+CSS+DOM+XML+asynchronous I/O+JavaScript to build desktop-quality applications inside the browser.

**Type:** Build
**Languages:** HTML, CSS, JavaScript, Python (HTML parser, form-encoder)
**Prerequisites:** Phase 12 Lesson 06 (Web architecture)
**Time:** ~130 minutes

## Learning Objectives

- Distinguish static HTML files on disk from dynamically generated pages and explain when each is appropriate.
- Read a small HTML document and identify the head, body, common tags (`<html>`, `<head>`, `<title>`, `<body>`, `<h1>`, `<p>`, `<a>`, `<img>`, `<form>`, `<input>`).
- Encode an HTML form submission as `application/x-www-form-urlencoded` and explain how the server decodes it.
- Compare CGI, PHP, JSP, ASP.NET for server-side dynamic generation.
- Sketch the AJAX model: how JavaScript + DOM + XMLHttpRequest enable desktop-quality Web apps.

## The Problem

The early Web only flowed one way — server to browser. Once people wanted to search catalogs, place orders, log into accounts, and see personalised feeds, the static-file model broke. The community added three solutions: **server-side generation** (CGI, PHP, JSP, ASP.NET run programs on the server that emit HTML), **client-side scripting** (JavaScript runs inside the browser to react to user input), and **AJAX** (the two combined, with asynchronous XML/JSON round-trips that don't refresh the page). Each has tradeoffs: server-side is the only way to touch the database; client-side is the only way to react before a network round-trip. You must understand all three to design and debug modern Web applications.

## The Concept

### Static HTML on disk

A static page is a file served verbatim:

```html
<html>
<head>
  <title>AMALGAMATED WIDGET, INC.</title>
</head>
<body>
  <h1>Welcome to AWI's Home Page</h1>
  <img src="http://www.widget.com/images/logo.gif" alt="AWI Logo">
  <p>We are so happy that you have chosen to visit
     <b>Amalgamated Widget's</b> home page.</p>
  <h2>Product information</h2>
  <ul>
    <li><a href="http://widget.com/products/big">Big widgets</a></li>
    <li><a href="http://widget.com/products/little">Little widgets</a></li>
  </ul>
</body>
</html>
```

HTML is a **markup language**: tags like `<b>` carry formatting commands (`<b>` = bold). The browser reads the file, applies the tags, and renders the result. Whitespace inside the body is collapsed by the parser — extra spaces and newlines have no effect on layout. To control layout precisely, use CSS.

The basic HTML vocabulary:

| Tag | Purpose | Example |
|-----|---------|---------|
| `<html>...</html>` | Document root | required by spec, tolerated if missing |
| `<head>...</head>` | Metadata container | contains `<title>`, `<link>`, `<meta>` |
| `<title>...</title>` | Window/tab title | not displayed in body |
| `<body>...</body>` | Visible content | everything the user sees |
| `<h1>` ... `<h6>` | Headings | h1 = most prominent, h6 = least |
| `<p>...</p>` | Paragraph | block-level, may add vertical spacing |
| `<b>...</b>` | Boldface | inline formatting |
| `<i>...</i>` | Italic | inline formatting |
| `<a href="...">` | Hyperlink | `href` is the URL |
| `<img src="...">` | Image | self-closing, has `alt` text |
| `<br>` | Line break | self-closing |
| `<hr>` | Horizontal rule | self-closing |
| `<ul>`, `<ol>`, `<li>` | Lists | unordered, ordered, list item |
| `<table>`, `<tr>`, `<td>` | Tables | HTML 3.0+ |
| `<form>`, `<input>` | Form | user input back to server |

Static pages can still be rich: a video file embedded with `<video src="...">` is part of a static page even though the video is many megabytes.

### HTML version history

The textbook's Figure 7-24 shows the feature progression:

| Feature | HTML 1.0 (1993) | HTML 2.0 | HTML 3.0 | HTML 4.0 | HTML 5.0 |
|---------|-----------------|----------|----------|----------|----------|
| Hyperlinks | yes | yes | yes | yes | yes |
| Images | yes | yes | yes | yes | yes |
| Lists | yes | yes | yes | yes | yes |
| Forms | — | yes | yes | yes | yes |
| Tables | — | — | yes | yes | yes |
| Style sheets | — | — | — | yes | yes |
| Scripting | — | — | — | yes | yes |
| Video / audio | — | — | — | — | yes |
| Inline vector (SVG) | — | — | — | — | yes |
| Canvas drawing | — | — | — | — | yes |
| Browser storage | — | — | — | — | yes |

HTML 5.0 is the modern lingua franca, consolidating video, audio, SVG, canvas, and offline storage without plug-ins.

### Forms — the first interactive primitive

Forms collect user input and POST it back to the server:

```html
<form ACTION="http://widget.com/cgi-bin/order.cgi" method=POST>
  <p>Name <input name="customer" size=46></p>
  <p>Street address <input name="address" size=40></p>
  <p>Credit card # <input name="cardno" size=10>
     Expires <input name="expires" size=4></p>
  <p>M/C <input name="cc" type=radio value="mastercard">
     VISA <input name="cc" type=radio value="visacard"></p>
  <p><input type=submit value="Submit order"></p>
</form>
```

When the user clicks **Submit**, the browser **encodes the form fields** as `application/x-www-form-urlencoded` and POSTs them to the form's `action` URL:

```
customer=John+Doe&address=100+Main+St.&city=White+Plains&
state=NY&country=USA&cardno=1234567890&expires=6/14&cc=mastercard&
product=cheap&express=on
```

Encoding rules:

- Fields separated by `&`.
- Each `name=value` pair URL-encoded; spaces become `+` (or `%20`), special chars become `%XX`.
- Checkboxes contribute their `name=value` only if checked.
- Radio buttons contribute only the selected one from each group.

This encoding is plain ASCII, fits SMTP-style transport constraints, and is trivial to parse.

### CSS — separating presentation from content

CSS rules apply visual styling to HTML elements:

```css
body { background-color: linen; color: navy; font-family: Arial; }
h1 { font-size: 200%; }
h2 { font-size: 150%; }
a  { color: #E2557A; text-decoration: none; }
```

A single CSS file can style thousands of pages by referencing it from each HTML head:

```html
<link rel="stylesheet" type="text/css" href="awistyle.css" />
```

CSS obeys the **cascading** rule: multiple rules can apply to one element, with more specific selectors overriding less specific ones.

### Server-side dynamic generation

When the page depends on user input or database state, the server runs a program:

**CGI** (RFC 3875, 1993) — the original mechanism:

```text
Browser POST /cgi-bin/order.cgi
Server  spawn /usr/lib/cgi-bin/order.cgi (separate process)
        pass form data via environment + stdin
        capture stdout as HTML response
```

Each request spawns a new process. Simple but expensive at scale.

**PHP** (1995) — script embedded in HTML, parsed by an Apache module:

```html
<html><body>
  <h1>Reply:</h1>
  Hello <?php echo $name; ?>.<br>
  Prediction: next year you will be <?php echo $age + 1; ?>.
</body></html>
```

The PHP interpreter scans for `<?php ... ?>` blocks, executes them, and emits the surrounding text verbatim. No process spawn per request — the interpreter stays loaded.

**JSP** (JavaServer Pages) — same idea, Java code:

```html
<html><body>
  <h1>Reply:</h1>
  Hello <%= request.getParameter("name") %>.<br>
</body></html>
```

**ASP.NET** (Microsoft) — same idea, .NET languages:

```html
<html><body>
  <h1>Reply:</h1>
  Hello <%= Request["name"] %>.<br>
</body></html>
```

The textbook summarises the choice between these as more **political** (open-source vs Microsoft) than technical.

### Client-side dynamic — JavaScript

JavaScript is a high-level scripting language that runs inside the browser. Despite the name, it shares almost nothing with Java:

```html
<html><head>
<script language="javascript" type="text/javascript">
function response(testForm) {
  var person = testForm.name.value;
  var years = eval(testForm.age.value) + 1;
  document.open();
  document.writeln("<html><body>Hello " + person + ".<br>");
  document.writeln("Prediction: next year you will be " + years + ".");
  document.writeln("</body></html>");
  document.close();
}
</script>
</head>
<body>
  <form>
    Please enter your name: <input type="text" name="name"><p>
    Please enter your age: <input type="text" name="age"><p>
    <input type="button" value="submit" onclick="response(this.form)">
  </form>
</body></html>
```

JavaScript can react to mouse moves, validate input before submission, and rewrite parts of the page. Crucially, it runs **before** any network round-trip — instant feedback.

### AJAX — Asynchronous JavaScript and XML

AJAX is not a language; it is a **set of five technologies** combined to enable responsive Web applications:

1. **HTML + CSS** to present information.
2. **DOM** (Document Object Model) — a tree representation of the page that programs can modify.
3. **XML or JSON** to exchange structured data with the server.
4. **Asynchronous HTTP** (the `XMLHttpRequest` API or the modern `fetch()`) so the page doesn't freeze while waiting.
5. **JavaScript** as the glue.

With AJAX, a map page can fetch new tiles from the server while the user scrolls, a chat page can push new messages without refreshing, and a search box can show completions on every keystroke. Gmail, Google Maps, and Google Docs are textbook AJAX applications.

### DOM — programmatic page access

The DOM is a tree API:

```text
html
 └── body
      └── form (action="action.php", method="post")
           ├── p
           │    └── input type="text" name="name"
           ├── p
           │    └── input type="text" name="age"
           └── input type="submit"
```

JavaScript can `document.getElementById("name").value = "Alice"` to read or modify any node. This is the foundation of AJAX: change parts of the page without reloading the whole thing.

### Putting it together

```text
Static (server returns file):
  GET /index.html -> 200 OK -> file from disk
  GET /style.css -> 200 OK -> file from disk

Server-side dynamic:
  POST /cgi-bin/order.cgi -> 200 OK -> stdout of program

Client-side dynamic:
  GET /index.html -> 200 OK -> HTML with <script>...</script>
  Browser executes JavaScript -> page interactivity without server

AJAX:
  GET /index.html -> 200 OK -> HTML + <script src="app.js"></script>
  Browser runs app.js, which does:
    GET /api/search?q=cat -> 200 OK -> JSON results
  JavaScript inserts results into DOM
```

## Build It

1. Run `python3 code/main.py` to encode and decode a sample HTML form submission, then parse a small static HTML file.
2. Create a one-page static site (HTML + CSS) and serve it locally with `python3 -m http.server 8000`. Open it in a browser and inspect the Network tab.
3. Add a `<form>` with a couple of inputs and watch the `application/x-www-form-urlencoded` body in the dev tools.
4. Inspect `assets/static-dynamic-web.svg` for the side-by-side architecture.

## Use It

| Task | Tool | What Good Looks Like |
|------|------|----------------------|
| View page source | Browser right-click "View Source" | HTML text, no rendered formatting |
| Inspect computed CSS | Browser dev tools Elements > Styles | Resolved values for each property |
| Trace a form POST | Browser dev tools Network | `Content-Type: application/x-www-form-urlencoded` |
| Test a static site | `python3 -m http.server` | No server-side processing observed |
| Validate HTML | https://validator.w3.org/ | No errors reported |

## Ship It

Build a static site under `outputs/` with three pages (`index.html`, `about.html`, `contact.html`), one shared `style.css`, and one HTML form (no server logic; just `mailto:` action). Document the file tree, line counts, and served-byte sizes. Start with [`outputs/prompt-static-dynamic-web.md`](../outputs/prompt-static-dynamic-web.md).

## Exercises

1. A page is served with `Cache-Control: max-age=86400` and `Last-Modified: Tue, 01 Jan 2025 12:00:00 GMT`. Will the browser refetch on the next visit one hour later?
2. The form's hidden field `<input type="hidden" name="csrf_token" value="x9f...">` is missing from the submission. What attack does this enable?
3. A static site has 100 pages of 5 KB each. The same content delivered by a single PHP page using `?id=1..100` is 1 KB. Compare cache efficiency.
4. Why does JavaScript's `eval()` on form input open an injection hole?
5. The page makes an AJAX call to `/api/users`. The server responds with `Content-Type: text/html` instead of `application/json`. What will the JavaScript do?
6. A `<form method="GET" action="/search">` submission with `<input name="q" value="cat">` produces the URL `https://example.com/search?q=cat`. Where in RFC 3986 is the `q=cat` part?

## Key Terms

| Term | Plain English | Technical meaning |
|------|---------------|-------------------|
| HTML | "Web page language" | HyperText Markup Language, current version HTML 5 |
| CSS | "style language" | Cascading Style Sheets, separates presentation |
| Tag | "formatting command" | `<b>...</b>`, `<p>...</p>`, etc. |
| Attribute | "tag parameter" | `src="..."`, `name="..."`, `type="..."` |
| Form | "input group" | `<form>` with named input fields |
| URL encoding | "escape special chars" | `application/x-www-form-urlencoded` |
| CGI | "old dynamic mechanism" | RFC 3875, spawn process per request |
| PHP | "embedded server script" | Preprocessor for HTML, runs in Apache |
| JavaScript | "browser scripting" | ECMA-262, runs in every modern browser |
| DOM | "page as tree" | Document Object Model for programmatic access |
| AJAX | "responsive Web apps" | Async JS + DOM + XML/JSON |
| XMLHttpRequest | "the AJAX API" | Browser API for async HTTP |

## Further Reading

- HTML 5.0 — W3C Recommendation, 2014
- CSS — Cascading Style Sheets specification, W3C
- RFC 3875 — The Common Gateway Interface (CGI)
- RFC 2318 — Defining the CSS Resource Type (text/css)
- ECMA-262 — ECMAScript Language Specification (JavaScript)
- DOM Living Standard — https://dom.spec.whatwg.org/
- MDN Web Docs — https://developer.mozilla.org/
- Flanagan, *JavaScript: The Definitive Guide*, 7th ed., O'Reilly 2020
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 7, Sections 7.3.2 to 7.3.3
