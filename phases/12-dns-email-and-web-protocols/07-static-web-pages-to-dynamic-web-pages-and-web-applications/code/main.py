#!/usr/bin/env python3
"""Static and dynamic web page generator with HTML parsing and CGI model.

Stdlib only, no network calls. Demonstrates four things:

1. A minimal HTML parser that extracts the document structure (head,
   body, headings, paragraphs, links, images, lists) from section
   7.3.2 (Fig. 7-23). Tags are tokenized and a simple DOM tree is
   built.
2. Static page generation: the page is a file on disk, identical every
   time it is fetched. The server reads it and returns it unchanged.
3. The CGI (Common Gateway Interface) model from RFC 3875: the server
   maps a URL to a program in cgi-bin, executes it as a separate
   process, passes form data as input, and returns the program's
   stdout as the HTTP response (section 7.3.3, Fig. 7-29).
4. Dynamic content pipeline: server-side script execution (PHP-like
   template expansion), form processing, and AJAX-style partial
   updates. Shows the difference between server-side (PHP/JSP/ASP)
   and client-side (JavaScript) dynamic generation from Fig. 7-35.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import html as html_module


@dataclass
class HTMLElement:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["HTMLElement"] = field(default_factory=list)
    text: str = ""
    parent: Optional["HTMLElement"] = None

    def find_all(self, tag: str) -> list["HTMLElement"]:
        result: list[HTMLElement] = []
        if self.tag == tag:
            result.append(self)
        for child in self.children:
            result.extend(child.find_all(tag))
        return result

    def render(self, indent: int = 0) -> str:
        prefix = "  " * indent
        attr_str = " ".join(f'{k}="{v}"' for k, v in self.attrs.items())
        if attr_str:
            opening = f"{prefix}<{self.tag} {attr_str}>"
        else:
            opening = f"{prefix}<{self.tag}>"
        lines = [opening]
        if self.text:
            lines.append(f"{prefix}  {self.text}")
        for child in self.children:
            lines.append(child.render(indent + 1))
        lines.append(f"{prefix}</{self.tag}>")
        return "\n".join(lines)


class HTMLParser:
    """A minimal HTML tag parser (not a full HTML5 parser)."""

    VOID_TAGS: set[str] = {"br", "hr", "img", "input", "meta", "link"}

    def parse(self, source: str) -> HTMLElement:
        self._source = source
        self._pos = 0
        root = HTMLElement(tag="root")
        self._parse_children(root)
        return root

    def _parse_children(self, parent: HTMLElement) -> None:
        while self._pos < len(self._source):
            if self._source[self._pos] == "<":
                if self._source[self._pos:self._pos + 4] == "<!--":
                    end = self._source.find("-->", self._pos)
                    if end == -1:
                        break
                    self._pos = end + 3
                    continue
                tag, attrs, self_closing = self._parse_tag()
                if tag.startswith("/"):
                    return
                element = HTMLElement(tag=tag, attrs=attrs)
                element.parent = parent
                parent.children.append(element)
                if tag in self.VOID_TAGS or self_closing:
                    continue
                self._parse_text(element)
                self._parse_children(element)
            else:
                self._parse_text(parent)

    def _parse_text(self, parent: HTMLElement) -> None:
        start = self._pos
        while self._pos < len(self._source) and self._source[self._pos] != "<":
            self._pos += 1
        text = self._source[start:self._pos].strip()
        if text and not parent.text:
            parent.text = html_module.unescape(text)
        elif text:
            parent.text += " " + html_module.unescape(text)

    def _parse_tag(self) -> tuple[str, dict[str, str], bool]:
        end = self._source.find(">", self._pos)
        if end == -1:
            self._pos = len(self._source)
            return "", {}, False
        raw = self._source[self._pos + 1:end]
        self._pos = end + 1
        self_closing = raw.endswith("/")
        if self_closing:
            raw = raw[:-1]
        parts = raw.split(maxsplit=1)
        tag = parts[0].lower() if parts else ""
        attrs: dict[str, str] = {}
        if len(parts) > 1:
            attr_str = parts[1]
            i = 0
            while i < len(attr_str):
                while i < len(attr_str) and attr_str[i] in " \t\n":
                    i += 1
                eq = attr_str.find("=", i)
                space = i
                while space < len(attr_str) and attr_str[space] not in " \t\n=":
                    space += 1
                if eq == -1 or eq > space:
                    name = attr_str[i:space]
                    attrs[name] = ""
                    i = space
                else:
                    name = attr_str[i:eq].strip()
                    i = eq + 1
                    if i < len(attr_str) and attr_str[i] in '"\'':
                        quote = attr_str[i]
                        end_q = attr_str.find(quote, i + 1)
                        if end_q == -1:
                            attrs[name] = attr_str[i + 1:]
                            break
                        attrs[name] = attr_str[i + 1:end_q]
                        i = end_q + 1
                    else:
                        sp = i
                        while sp < len(attr_str) and attr_str[sp] not in " \t\n":
                            sp += 1
                        attrs[name] = attr_str[i:sp]
                        i = sp
        return tag, attrs, self_closing


STATIC_HTML = """\
<html>
<head><title>AWI Home Page</title></head>
<body>
<h1>Welcome to AWI's Home Page</h1>
<img src="logo.gif" alt="AWI Logo">
<p>We are happy that you have chosen to visit <b>Amalgamated Widget's</b>
home page. We hope you will find all the information you need here.</p>
<hr>
<h2>Product information</h2>
<ul>
<li><a href="http://widget.com/products/big">Big widgets</a></li>
<li><a href="http://widget.com/products/little">Little widgets</a></li>
</ul>
<h2>Contact information</h2>
<ul>
<li>By telephone: 1-800-WIDGETS</li>
<li>By email: info@amalgamated-widget.com</li>
</ul>
</body>
</html>
"""


FORM_HTML = """\
<html>
<head><title>Widget Order Form</title></head>
<body>
<h1>Widget Order Form</h1>
<form action="/cgi-bin/order.cgi" method="POST">
<p>Name <input name="customer" size="46"></p>
<p>Street address <input name="address" size="40"></p>
<p>Credit card # <input name="cardno" size="10">
Expires <input name="expires" size="4"></p>
<p><input type="submit" value="Submit order"></p>
</form>
</body>
</html>
"""


@dataclass
class StaticPage:
    path: str
    content: str
    content_type: str = "text/html"

    def serve(self) -> tuple[int, dict[str, str], str]:
        return 200, {
            "Content-Type": self.content_type,
            "Content-Length": str(len(self.content)),
        }, self.content


class CGIServer:
    """Simulates the CGI execution model (RFC 3875)."""

    def __init__(self) -> None:
        self.scripts: dict[str, object] = {}

    def register(self, path: str, handler: object) -> None:
        self.scripts[path] = handler

    def execute(self, path: str, form_data: dict[str, str],
                env: Optional[dict[str, str]] = None) -> tuple[int, dict[str, str], str]:
        handler = self.scripts.get(path)
        if handler is None:
            return 404, {"Content-Type": "text/plain"}, "CGI script not found"
        cgi_env = {
            "REQUEST_METHOD": "POST",
            "QUERY_STRING": "",
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "PATH_INFO": path,
        }
        if env:
            cgi_env.update(env)
        result = handler(form_data, cgi_env)
        return 200, {"Content-Type": "text/html"}, result


def order_cgi(form: dict[str, str], env: dict[str, str]) -> str:
    """CGI handler that processes the widget order form."""
    customer = form.get("customer", "Unknown")
    address = form.get("address", "(no address)")
    cardno = form.get("cardno", "")
    masked_card = f"****{cardno[-4:]}" if len(cardno) >= 4 else cardno
    return f"""\
<html>
<body>
<h1>Order Confirmation</h1>
<p>Thank you for your order, <b>{html_module.escape(customer)}</b>!</p>
<p>Shipping to: {html_module.escape(address)}</p>
<p>Card on file: {masked_card}</p>
<p>Your order will ship in 3-5 business days.</p>
</body>
</html>"""


class DynamicPageGenerator:
    """Server-side dynamic page generation (PHP/JSP/ASP model)."""

    def __init__(self) -> None:
        self.templates: dict[str, str] = {}

    def register_template(self, name: str, template: str) -> None:
        self.templates[name] = template

    def render(self, name: str, context: dict[str, str]) -> str:
        template = self.templates.get(name, "")
        result = template
        for key, value in context.items():
            token = f"{{{{{key}}}}}"
            result = result.replace(token, html_module.escape(value))
        result = result.replace("{{timestamp}}", "2024-01-15 12:00:00")
        return result


def encode_form(form: dict[str, str]) -> str:
    """Encode form data as URL-encoded string (Fig. 7-26 format)."""
    pairs: list[str] = []
    for key, value in form.items():
        pairs.append(f"{key}={value.replace(' ', '+')}")
    return "&".join(pairs)


def main() -> None:
    print("=" * 70)
    print("Static Web Pages (section 7.3.2)")
    print("=" * 70)

    print("\n--- HTML parsing (Fig. 7-23 structure) ---")
    parser = HTMLParser()
    doc = parser.parse(STATIC_HTML)
    heads = doc.find_all("head")
    bodies = doc.find_all("body")
    h1s = doc.find_all("h1")
    h2s = doc.find_all("h2")
    links = doc.find_all("a")
    imgs = doc.find_all("img")
    lists = doc.find_all("ul")
    forms = doc.find_all("form")
    inputs = doc.find_all("input")
    print(f"  head elements: {len(heads)}")
    print(f"  body elements: {len(bodies)}")
    print(f"  h1 headings:   {len(h1s)} -> {h1s[0].text if h1s else ''}")
    print(f"  h2 headings:   {len(h2s)} -> {[h.text for h in h2s]}")
    print(f"  links (a):      {len(links)}")
    for link in links:
        href = link.attrs.get("href", "")
        text = link.text
        print(f"    href={href}  text={text!r}")
    print(f"  images (img):   {len(imgs)}")
    for img in imgs:
        print(f"    src={img.attrs.get('src', '')}  alt={img.attrs.get('alt', '')!r}")
    print(f"  lists (ul):     {len(lists)}")

    print("\n--- Static page serving ---")
    page = StaticPage("/index.html", STATIC_HTML)
    status, headers, body = page.serve()
    print(f"  GET /index.html -> {status}")
    for k, v in headers.items():
        print(f"    {k}: {v}")
    print(f"  Body: {len(body)} bytes (identical every fetch)")

    print(f"\n{'=' * 70}")
    print("Dynamic Web Pages and Web Applications (section 7.3.3)")
    print(f"{'=' * 70}")

    print("\n--- CGI (Common Gateway Interface, RFC 3875) ---")
    cgi = CGIServer()
    cgi.register("/cgi-bin/order.cgi", order_cgi)

    form_data = {
        "customer": "John Doe",
        "address": "100 Main St.",
        "cardno": "1234567890",
        "expires": "6/14",
    }
    encoded = encode_form(form_data)
    print(f"  Form data encoded: {encoded[:80]}...")
    print(f"  CGI environment:")
    print(f"    REQUEST_METHOD=POST  PATH_INFO=/cgi-bin/order.cgi")
    print(f"    CONTENT_TYPE=application/x-www-form-urlencoded")
    status, headers, cgi_body = cgi.execute("/cgi-bin/order.cgi", form_data)
    print(f"  CGI response: {status}")
    for k, v in headers.items():
        print(f"    {k}: {v}")
    print(f"  CGI output ({len(cgi_body)} bytes):")
    for line in cgi_body.splitlines():
        print(f"    | {line}")

    print("\n--- Form parsing (Fig. 7-25 & 7-26) ---")
    form_doc = parser.parse(FORM_HTML)
    form_elements = form_doc.find_all("form")
    for f in form_elements:
        print(f"  form action={f.attrs.get('action', '')}  method={f.attrs.get('method', '')}")
    form_inputs = form_doc.find_all("input")
    for inp in form_inputs:
        itype = inp.attrs.get("type", "text")
        name = inp.attrs.get("name", "")
        size = inp.attrs.get("size", "")
        value = inp.attrs.get("value", "")
        print(f"    input type={itype:<8} name={name:<12} size={size:<4} value={value!r}")

    print("\n--- Server-side dynamic generation (PHP model) ---")
    generator = DynamicPageGenerator()
    generator.register_template("storefront", """\
<html>
<body>
<h1>Welcome back, {{name}}!</h1>
<p>Based on your history, you might like:</p>
<ul>
<li>{{recommendation}}</li>
</ul>
<p>Generated at: {{timestamp}}</p>
</body>
</html>""")
    for user, rec in [("Alice", "Mystery novels"), ("Bob", "Cookbooks"), ("Carol", "Sci-fi")]:
        html = generator.render("storefront", {"name": user, "recommendation": rec})
        print(f"\n  Rendered for {user} ({len(html)} bytes):")
        for line in html.splitlines()[:6]:
            print(f"    | {line}")

    print("\n--- Client-side dynamic generation (JavaScript model) ---")
    js_example = """\
<script>
function response(form) {
  var person = form.name.value;
  var years = parseInt(form.age.value) + 1;
  document.open();
  document.writeln("Hello " + person + ".");
  document.writeln("Prediction: next year you will be " + years + ".");
  document.close();
}
</script>"""
    print("  JavaScript runs in the browser (no server round-trip):")
    for line in js_example.splitlines():
        print(f"    {line}")

    print("\n--- Server-side vs Client-side comparison ---")
    comparisons = [
        ("PHP/JSP/ASP", "Server", "Interaction with database, form processing"),
        ("JavaScript", "Client", "Mouse events, DOM updates, responsive UI"),
        ("AJAX", "Both", "Async data exchange, partial page updates"),
    ]
    for tech, where, use_case in comparisons:
        print(f"  {tech:<14} {where:<10} {use_case}")

    print("\n--- HTML version features (Fig. 7-24) ---")
    features = [
        ("Hyperlinks", "1.0", "2.0", "3.0", "4.0", "5.0"),
        ("Images", "1.0", "2.0", "3.0", "4.0", "5.0"),
        ("Tables", "", "", "3.0", "4.0", "5.0"),
        ("Forms", "", "2.0", "3.0", "4.0", "5.0"),
        ("Style sheets", "", "", "", "4.0", "5.0"),
        ("Scripting", "", "", "", "4.0", "5.0"),
        ("Video and audio", "", "", "", "", "5.0"),
        ("Drawing canvas", "", "", "", "", "5.0"),
    ]
    print(f"  {'Feature':<22} {'1.0':>4} {'2.0':>4} {'3.0':>4} {'4.0':>4} {'5.0':>4}")
    for feature, *versions in features:
        row = "  " + f"{feature:<22}"
        for v in versions:
            row += f" {v:>4}" if v else f" {' ':>4}"
        print(row)


if __name__ == "__main__":
    main()