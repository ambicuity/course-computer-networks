#!/usr/bin/env python3
"""Mobile web challenges and web search simulator (sections 7.3.5-7.3.6).

Stdlib only, no network calls. Demonstrates four things:

1. Mobile web challenges from section 7.3.5: small screens, limited
   input, low bandwidth, intermittent connectivity, limited computing
   power. A responsive-design detector checks HTML for viewport meta
   tags and CSS media queries.
2. Viewport meta parser: extracts width, initial-scale, maximum-scale
   from <meta name="viewport" content="..."> tags, which tell the
   browser how to scale the page for mobile screens.
3. Mobile-vs-desktop resource comparison: given a page's resources
   (images, scripts, stylesheets), compute the total payload size for
   desktop vs mobile versions, showing the bandwidth savings from
   responsive design and transcoding.
4. Web search simulator (section 7.3.6): a mini crawler that fetches
   pages and extracts links, an indexer that builds a term-document
   matrix, and a ranker that scores documents by TF-IDF (term
   frequency * inverse document frequency), with PageRank-style link
   counting as a secondary signal.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import math
import re
from collections import Counter


MOBILE_CHALLENGES: list[tuple[str, str]] = [
    ("Small screens", "Preclude large pages and large images"),
    ("Limited input", "Tedious to enter URLs or lengthy input"),
    ("Low bandwidth", "Wireless links, especially 3G, are slow and expensive"),
    ("Intermittent connectivity", "Connection may drop during page load"),
    ("Limited computing", "Battery, size, heat, and cost constraints"),
]


@dataclass
class ViewportMeta:
    width: str = "device-width"
    initial_scale: float = 1.0
    maximum_scale: float = 10.0
    minimum_scale: float = 0.25
    user_scalable: bool = True
    height: str = ""

    @classmethod
    def parse(cls, content: str) -> "ViewportMeta":
        vp = cls()
        for prop in content.split(","):
            prop = prop.strip()
            if "=" not in prop:
                continue
            key, _, val = prop.partition("=")
            key = key.strip().lower()
            val = val.strip()
            if key == "width":
                vp.width = val
            elif key == "height":
                vp.height = val
            elif key == "initial-scale":
                try:
                    vp.initial_scale = float(val)
                except ValueError:
                    pass
            elif key == "maximum-scale":
                try:
                    vp.maximum_scale = float(val)
                except ValueError:
                    pass
            elif key == "minimum-scale":
                try:
                    vp.minimum_scale = float(val)
                except ValueError:
                    pass
            elif key == "user-scalable":
                vp.user_scalable = val.lower() in ("yes", "true", "1")
        return vp

    def is_responsive(self) -> bool:
        return self.width == "device-width" or self.width.endswith("%")


def extract_viewport(html: str) -> Optional[ViewportMeta]:
    """Extract viewport meta tag from HTML."""
    pattern = r'<meta\s+name=["\']viewport["\']\s+content=["\']([^"\']+)["\']'
    match = re.search(pattern, html, re.IGNORECASE)
    if match:
        return ViewportMeta.parse(match.group(1))
    return None


def detect_media_queries(css: str) -> list[str]:
    """Find @media rules in CSS, returning the media conditions."""
    pattern = r'@media\s+([^{]+)\{'
    return re.findall(pattern, css)


@dataclass
class Resource:
    url: str
    type: str
    desktop_size: int
    mobile_size: int

    def savings(self) -> int:
        return self.desktop_size - self.mobile_size


def analyze_page_resources(resources: list[Resource]) -> dict[str, int]:
    """Compute total payload sizes for desktop vs mobile."""
    desktop_total = sum(r.desktop_size for r in resources)
    mobile_total = sum(r.mobile_size for r in resources)
    return {
        "desktop_bytes": desktop_total,
        "mobile_bytes": mobile_total,
        "savings_bytes": desktop_total - mobile_total,
        "savings_percent": round((1 - mobile_total / desktop_total) * 100, 1) if desktop_total else 0,
    }


@dataclass
class WebPageDoc:
    url: str
    title: str
    text: str
    links: list[str] = field(default_factory=list)

    def terms(self) -> list[str]:
        """Extract lowercase word tokens from text."""
        return re.findall(r'[a-z]+', self.text.lower())


class Crawler:
    """A mini web crawler that follows links (simulated)."""

    def __init__(self) -> None:
        self.visited: set[str] = set()
        self.pages: dict[str, WebPageDoc] = {}

    def crawl(self, seed_pages: dict[str, WebPageDoc]) -> None:
        queue = list(seed_pages.keys())
        while queue:
            url = queue.pop(0)
            if url in self.visited:
                continue
            self.visited.add(url)
            page = seed_pages[url]
            self.pages[url] = page
            for link in page.links:
                if link in seed_pages and link not in self.visited:
                    queue.append(link)


class Indexer:
    """Builds a term-document index from crawled pages."""

    def __init__(self) -> None:
        self.documents: dict[str, WebPageDoc] = {}
        self.term_freqs: dict[str, Counter] = {}
        self.doc_freq: dict[str, int] = {}
        self.inverted_index: dict[str, list[str]] = {}

    def index(self, pages: dict[str, WebPageDoc]) -> None:
        self.documents = pages
        for url, page in pages.items():
            terms = page.terms()
            tf = Counter(terms)
            self.term_freqs[url] = tf
            for term in tf:
                self.doc_freq[term] = self.doc_freq.get(term, 0) + 1
                self.inverted_index.setdefault(term, []).append(url)

    def tfidf(self, term: str, url: str) -> float:
        """Compute TF-IDF for a term in a document."""
        tf = self.term_freqs.get(url, Counter()).get(term, 0)
        if tf == 0:
            return 0.0
        n_docs = len(self.documents)
        df = self.doc_freq.get(term, 0)
        if df == 0:
            return 0.0
        idf = math.log(n_docs / df) + 1
        return tf * idf


class Ranker:
    """Ranks documents by TF-IDF and link-based importance (PageRank-lite)."""

    def __init__(self, indexer: Indexer) -> None:
        self.indexer = indexer
        self.link_counts: dict[str, int] = {}

    def compute_link_scores(self) -> None:
        """Count inbound links as a simple importance signal."""
        counts: dict[str, int] = {url: 0 for url in self.indexer.documents}
        for url, page in self.indexer.documents.items():
            for link in page.links:
                if link in counts:
                    counts[link] += 1
        self.link_counts = counts

    def search(self, query: str, limit: int = 5) -> list[tuple[str, float, float]]:
        """Search for query terms, returning (url, tfidf_score, link_score)."""
        query_terms = re.findall(r'[a-z]+', query.lower())
        scores: dict[str, float] = {}
        for url in self.indexer.documents:
            total_tfidf = sum(self.indexer.tfidf(term, url) for term in query_terms)
            link_score = self.link_counts.get(url, 0)
            scores[url] = total_tfidf
        ranked = sorted(scores.items(), key=lambda x: (-x[1], -self.link_counts.get(x[0], 0)))
        results: list[tuple[str, float, float]] = []
        for url, tfidf_score in ranked[:limit]:
            if tfidf_score > 0:
                results.append((url, tfidf_score, self.link_counts.get(url, 0)))
        return results


def main() -> None:
    print("=" * 70)
    print("The Mobile Web (section 7.3.5)")
    print("=" * 70)

    print("\n--- Mobile web challenges ---")
    for challenge, desc in MOBILE_CHALLENGES:
        print(f"  {challenge:<28} {desc}")

    print("\n--- Viewport meta parser ---")
    viewports = [
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        '<meta name="viewport" content="width=320, initial-scale=0.5, maximum-scale=2.0">',
        '<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">',
    ]
    for vp_html in viewports:
        vp = extract_viewport(vp_html)
        if vp:
            print(f"  {vp_html}")
            print(f"    width={vp.width}  initial_scale={vp.initial_scale}  "
                  f"max_scale={vp.maximum_scale}  user_scalable={vp.user_scalable}  "
                  f"responsive={vp.is_responsive()}")

    print("\n--- Responsive design detection ---")
    sample_html = """\
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Responsive Site</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<h1>Hello</h1>
<img src="logo.png" alt="Logo">
</body>
</html>"""
    vp = extract_viewport(sample_html)
    print(f"  Has viewport meta: {vp is not None}")
    if vp:
        print(f"  Width: {vp.width}")
        print(f"  Responsive: {vp.is_responsive()}")

    sample_css = """
body { font-family: Arial; }
@media (max-width: 768px) { body { font-size: 14px; } }
@media (min-width: 769px) and (max-width: 1200px) { body { font-size: 16px; } }
@media print { body { color: black; } }
"""
    queries = detect_media_queries(sample_css)
    print(f"  CSS @media rules ({len(queries)}):")
    for q in queries:
        print(f"    @media {q.strip()}")

    print("\n--- Mobile vs desktop resource comparison ---")
    resources = [
        Resource("logo.png", "image", 250000, 50000),
        Resource("hero.jpg", "image", 800000, 150000),
        Resource("style.css", "stylesheet", 45000, 30000),
        Resource("app.js", "script", 320000, 180000),
        Resource("analytics.js", "script", 120000, 120000),
    ]
    stats = analyze_page_resources(resources)
    print(f"  {'Resource':<20} {'Type':<12} {'Desktop':>10} {'Mobile':>10} {'Saved':>10}")
    for r in resources:
        print(f"  {r.url:<20} {r.type:<12} {r.desktop_size:>10,} {r.mobile_size:>10,} {r.savings():>10,}")
    print(f"  {'TOTAL':<20} {'':12} {stats['desktop_bytes']:>10,} {stats['mobile_bytes']:>10,} "
          f"{stats['savings_bytes']:>10,}")
    print(f"  Bandwidth savings: {stats['savings_percent']}%")

    print("\n--- Approaches to mobile web ---")
    approaches = [
        ("WAP", "Separate protocol stack for wireless (largely abandoned)"),
        ("Same protocols", "Run HTTP/TCP/IP with header compression (ROHC)"),
        ("Mobile content", "Server detects User-Agent, returns mobile-friendly pages"),
        ("Transcoding", "Intermediary transforms desktop content for mobile"),
        ("XHTML Basic", "Stripped-down HTML subset for constrained devices"),
    ]
    for approach, desc in approaches:
        print(f"  {approach:<18} {desc}")

    print(f"\n{'=' * 70}")
    print("Web Search (section 7.3.6)")
    print(f"{'=' * 70}")

    print("\n--- Crawling: build the page database ---")
    seed_pages = {
        "http://cisco.com": WebPageDoc(
            "http://cisco.com", "Cisco Systems",
            "Cisco Systems is a leading manufacturer of networking equipment "
            "including routers switches and wireless access points. "
            "Cisco networks power the internet.",
            ["http://cisco.com/products", "http://cisco.com/about"]),
        "http://cisco.com/products": WebPageDoc(
            "http://cisco.com/products", "Cisco Products",
            "Cisco routers and switches for enterprise networks. "
            "Cisco wireless access points and security appliances.",
            ["http://cisco.com"]),
        "http://cisco.com/about": WebPageDoc(
            "http://cisco.com/about", "About Cisco",
            "Cisco Systems was founded in 1984. Cisco builds networking "
            "infrastructure for the internet.",
            ["http://cisco.com"]),
        "http://juniper.net": WebPageDoc(
            "http://juniper.net", "Juniper Networks",
            "Juniper Networks makes networking equipment and routers. "
            "Juniper competes with Cisco in the enterprise networking market.",
            ["http://juniper.net/products"]),
        "http://juniper.net/products": WebPageDoc(
            "http://juniper.net/products", "Juniper Products",
            "Juniper routers and switches. Juniper networking solutions.",
            ["http://juniper.net"]),
        "http://example.com/blog": WebPageDoc(
            "http://example.com/blog", "Networking Blog",
            "A blog about networking topics including Cisco and Juniper routers, "
            "switches, and network security.",
            ["http://cisco.com", "http://juniper.net"]),
    }

    crawler = Crawler()
    crawler.crawl(seed_pages)
    print(f"  Crawled {len(crawler.visited)} pages:")
    for url, page in crawler.pages.items():
        print(f"    {url} -> '{page.title}' ({len(page.links)} links)")

    print("\n--- Indexing: build term-document matrix ---")
    indexer = Indexer()
    indexer.index(crawler.pages)
    print(f"  Indexed {len(indexer.documents)} documents")
    print(f"  Vocabulary size: {len(indexer.doc_freq)} unique terms")
    print(f"  Top terms by document frequency:")
    for term, df in sorted(indexer.doc_freq.items(), key=lambda x: -x[1])[:10]:
        print(f"    {term:<20} df={df}")

    print("\n--- Ranking: TF-IDF + link scoring ---")
    ranker = Ranker(indexer)
    ranker.compute_link_scores()
    print(f"  Link scores (inbound links):")
    for url, count in sorted(ranker.link_counts.items(), key=lambda x: -x[1]):
        print(f"    {url:<40} links={count}")

    queries = ["cisco routers", "networking equipment", "juniper switches"]
    for query in queries:
        print(f"\n--- Search: '{query}' ---")
        results = ranker.search(query)
        if results:
            for rank, (url, tfidf, links) in enumerate(results, 1):
                title = indexer.documents[url].title
                print(f"  [{rank}] {title}")
                print(f"      URL: {url}")
                print(f"      TF-IDF: {tfidf:.2f}  Links: {links}")
        else:
            print(f"  No results found.")

    print(f"\n{'=' * 70}")
    print("Search Engine Components Summary")
    print(f"{'=' * 70}")
    components = [
        ("Crawler", "Traverses the Web by following links to find pages"),
        ("Indexer", "Builds a term-document matrix for fast lookup"),
        ("Ranker", "Scores documents by TF-IDF and link importance"),
        ("Query", "Processes user search terms against the index"),
        ("Advertising", "Targeted ads matched to search terms (auction-based)"),
    ]
    for comp, desc in components:
        print(f"  {comp:<14} {desc}")


if __name__ == "__main__":
    main()