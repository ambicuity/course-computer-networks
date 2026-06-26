# The DNS Name Space

> DNS maps human-readable names to IP addresses using a hierarchical, tree-structured namespace managed since 1998 by ICANN. The Internet is divided into over 250 top-level domains split into generic TLDs (com, edu, gov, org, net, and newer ones like aero, biz, mobi, pro) and country TLDs (one per ISO 3166 country, e.g., uk, jp, nl, us). Each domain is named by the path from itself up to the unnamed root, with components separated by dots. Absolute names end with a trailing dot (eng.cisco.com.) while relative names do not. Component names are case-insensitive, up to 63 characters each, with full path names capped at 255 characters. Creating a subdomain requires permission only from the parent domain — once registered, a domain can freely create subdomains beneath it. The namespace follows organizational boundaries, not physical topology: two departments sharing a LAN can have distinct domains, and a department split across buildings shares one domain. The original ARPANET approach (a single hosts.txt file fetched nightly) could not scale to millions of hosts, so DNS was invented in 1983 (RFCs 1034, 1035, 2181) as a hierarchical, distributed database.

**Type:** Build
**Languages:** dig, HTTP, Wireshark, Python
**Prerequisites:** Phase 11 (TCP, UDP), Phase 9 (IP addressing)
**Time:** ~90 minutes

## Learning Objectives

- Diagram the DNS namespace tree from root through TLDs to leaf domains, labeling the generic and country TLDs.
- Explain the difference between absolute (FQDN) and relative domain names, including the trailing-dot convention.
- Calculate whether a domain name is valid given the 63-character component limit and 255-character full-path limit.
- Describe how ICANN, registrars, and the first-come-first-served policy interact, and why cybersquatting exists.
- Trace why the namespace follows organizational, not physical, network boundaries.

## The Problem

A user types `www.cs.washington.edu` into a browser. The network only understands IP addresses. Something must convert that human-readable name into `128.208.3.88`. The original ARPANET solution — a nightly-downloaded hosts.txt file listing every machine — worked for a few hundred timesharing machines but collapsed under millions of hosts due to file size, update latency, and name conflicts. You need a scalable, hierarchical, distributed naming system.

## The Concept

### The hierarchical tree structure

The DNS namespace is a tree. The root is unnamed (written as a single dot). Below the root sit top-level domains. Below those sit second-level domains, and so on. Each node is a domain; each domain can have subdomains. A leaf domain may contain a single host or represent a company with thousands of hosts.

```
Root (.)
├── Generic TLDs: com, edu, gov, org, net, aero, biz, mobi, pro, ...
├── Country TLDs: au, jp, uk, us, nl, ...
│
└── com
    └── cisco
        └── eng         → eng.cisco.com
    └── washington (edu)
        └── cs
            └── robot   → robot.cs.washington.edu
```

The path from any node upward to the root forms its domain name. Components are separated by dots. Because the path is unique, `eng.cisco.com` cannot conflict with `eng.washington.edu` — they occupy different branches of the tree.

### Generic top-level domains

The generic TLDs were created starting in 1985. Some are restricted (only qualifying organizations can register), others are open to anyone:

| Domain | Intended use | Start | Restricted? |
|--------|-------------|-------|-------------|
| com | Commercial | 1985 | No |
| edu | Educational institutions | 1985 | Yes |
| gov | Government | 1985 | Yes |
| net | Network providers | 1985 | No |
| org | Non-profit organizations | 1985 | No |
| aero | Air transport | 2001 | Yes |
| biz | Businesses | 2001 | No |
| info | Informational | 2002 | No |
| pro | Professionals | 2002 | Yes |
| mobi | Mobile devices | 2005 | Yes |
| xxx | Sex industry | 2010 | No |

The restrictions spark policy debates. Is `pro` for doctors only, or also plumbers and tattoo artists? ICANN adjudicates these questions as new TLDs are proposed.

### Country domains and internationalization

Every country has a two-letter code per ISO 3166 (uk, jp, us, nl, au). Internationalized domain names using non-Latin alphabets (Arabic, Cyrillic, Chinese) were introduced in 2010. Countries organize their subdomains differently: Japan uses `ac.jp` (academic) and `co.jp` (commercial), mirroring edu and com. The Netherlands puts all organizations directly under `nl` without this split.

```
cs.washington.edu  → University of Washington, U.S.
cs.vu.nl            → Vrije Universiteit, Netherlands
cs.keio.ac.jp       → Keio University, Japan
```

### Absolute versus relative names

An absolute domain name (FQDN, Fully Qualified Domain Name) always ends with a trailing dot: `eng.cisco.com.` The trailing dot represents the root. A relative name lacks the trailing dot and must be interpreted in context — a host configured with a default domain `cs.washington.edu` can resolve the relative name `robot` as `robot.cs.washington.edu.`

### Naming rules and limits

| Rule | Value |
|------|-------|
| Component max length | 63 characters |
| Full path max length | 255 characters |
| Case sensitivity | Case-insensitive (edu = Edu = EDU) |
| Character set | Letters, digits, hyphens (not at start/end) |
| Separator | Dot (.) |

The `code/main.py` script validates domain names against these rules and walks the tree structure.

### Creating and delegating domains

To create a new subdomain, you only need permission from the parent domain. If a VLSI group at UW wants `vlsi.cs.washington.edu`, they ask whoever manages `cs.washington.edu`. Once registered, `vlsi.cs.washington.edu` can freely create subdomains like `lab1.vlsi.cs.washington.edu` without consulting anyone higher up. This delegation model prevents name conflicts without a single global bottleneck.

### Organizational, not physical, boundaries

Naming follows organizational boundaries, not network topology. If CS and EE departments share a building and a LAN, they can still have distinct domains (`cs.washington.edu` and `ee.washington.edu`). Conversely, if CS is split across two buildings, all hosts belong to one domain. The namespace is a logical overlay, decoupled from physical connectivity.

### The economics and politics of names

Domain names have monetary value. Tuvalu sold its `tv` country code for $50 million because it suits television sites. Virtually every English word is taken in `com`. Cybersquatting — registering a domain only to resell at a higher price — is legal as long as no trademark is violated. Disputes are resolved by ICANN policies still being refined.

## Build It

1. Run `python3 code/main.py` to validate sample domain names against the naming rules and visualize the tree traversal.
2. Use `dig` to explore the hierarchy: `dig . NS` shows root servers; `dig com. NS` shows com servers.
3. Try resolving an absolute name: `dig robot.cs.washington.edu.` — note the trailing dot.
4. Compare with a relative lookup using your system's default search domain.
5. Inspect the SVG (`assets/the-dns-name-space.svg`) for the tree structure diagram.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|----------------------|
| Validate a domain name | Component lengths ≤ 63, total ≤ 255 | Script returns valid/invalid with reason |
| Identify TLD type | dig output, IANA registry | Correctly classify as generic or country |
| Trace delegation path | dig +trace output from root to leaf | Each step matches the hierarchy |
| Distinguish absolute vs relative | Trailing dot present/absent | FQDN resolves without search domain appended |

## Ship It

Create a domain-name validation toolkit under `outputs/`. Include a script that checks any input against all naming rules and a tree-walk diagram showing the resolution path from root to a leaf domain. Start with [`outputs/prompt-the-dns-name-space.md`](../outputs/prompt-the-dns-name-space.md).

## Exercises

1. Validate `a-really-long-component-name-that-exactly-hits-63-chars.example.com` — is it valid? What about one character longer?
2. Why does `eng.cisco.com` not conflict with `eng.washington.edu`? Explain using the tree structure.
3. Run `dig +trace www.cs.washington.edu` and annotate each step with the zone being queried. Which servers are authoritative at each level?
4. If a company has offices in Tokyo, Amsterdam, and Seattle, should they use one domain or three? What are the tradeoffs?
5. Explain why DNS follows organizational boundaries rather than physical network topology. Give a concrete example where this matters.
6. Research the `tv` domain sale by Tuvalu. What does this tell you about the economic value of the namespace?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| FQDN | "the full domain name" | Absolute name ending with a dot, unambiguous from root |
| TLD | "the .com part" | Top-level domain: generic (com, org) or country (uk, jp) |
| ICANN | "the DNS people" | Internet Corporation for Assigned Names and Numbers, manages root since 1998 |
| Cybersquatting | "domain flipping" | Registering a name to resell, legal if no trademark violated |
| Relative name | "partial domain" | Name without trailing dot, resolved via search domain context |
| Domain | "a website name" | A node in the DNS tree and all nodes beneath it |
| Registrar | "where you buy domains" | Entity appointed by ICANN to register names in a TLD |

## Further Reading

- RFC 1034 — Domain Names: Concepts and Facilities
- RFC 1035 — Domain Names: Implementation and Specification
- RFC 2181 — Clarifications to the DNS Specification
- ICANN — www.icann.org
- IANA TLD Registry — www.iana.org/domains/root/db
- ISO 3166 — Country codes standard
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 7, Section 7.1.1