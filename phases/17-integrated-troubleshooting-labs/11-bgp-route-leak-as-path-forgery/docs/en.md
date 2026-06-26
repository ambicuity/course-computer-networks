# BGP Route Leak and AS Path Forgery

> A misconfigured downstream announces a prefix it does not own; the global table reroutes half a country through a small regional ISP for 47 minutes. The victim notices when its users see 220 ms latency to its own service and 12% packet loss. The BGP UPDATE is a single Type 2 message (RFC 4271 §4.3) carrying NLRI (Network Layer Reachability Information, the prefix + length) and the path attributes `AS_PATH` (Type Code 2, well-known mandatory), `NEXT_HOP` (Type Code 3, well-known mandatory), `ORIGIN` (Type Code 1, well-known mandatory: IGP, EGP, or INCOMPLETE), `MULTI_EXIT_DISC` (Type Code 4, optional non-transitive), and (if the operator is good) `COMMUNITIES` (Type Code 8, optional transitive, RFC 1997). The leaking AS prepends its own ASN to `AS_PATH`, but since the leak comes from a *customer* AS, most transit providers' import policies trust it: customers are assumed to announce only their own space. Without RPKI Route Origin Validation (RFC 6811) — and a ROA (Route Origin Authorization) in RFC 6480 covering the prefix — the receiver has no cryptographic reason to reject the route. In the 2008 Pakistan Telecom / YouTube incident, AS17557 originated `208.65.153.0/24` (a /22) as a /24, creating a more-specific hijack. In 2018 an Amazon route leaked via an eBGP misconfiguration at a partner AS rerouted AWS DNS through a third party for 2 hours. This lab reproduces both classes — a *route leak* (customer re-announces a transit-learned prefix) and an *AS path forgery / origin hijack* (attacker claims a prefix with a forged origin AS) — and shows how RPKI ROV turns the second into an `Invalid` verdict that any well-run network should reject.

**Type:** Lab
**Languages:** Python, shell, whois, looking-glass queries
**Prerequisites:** Phase 9 BGP lesson, Phase 17 lesson 10 (dual-stack), RFC 4271/6480/6811/7454
**Time:** ~110 minutes

## Learning Objectives

- Decode a BGP UPDATE message: identify the withdrawn routes length, the NLRI, and the path attributes by type code (1 ORIGIN, 2 AS_PATH, 3 NEXT_HOP, 4 MED, 5 LOCAL_PREF, 8 COMMUNITIES).
- Read an `AS_PATH` and determine origin vs transit: the leftmost ASN is the most recent (next hop), the rightmost is the origin (the AS that originated the prefix).
- Distinguish a *route leak* (real origin ASN present in path but the announcing AS is a customer that learned the route via one transit and re-advertised to another) from an *AS path forgery / origin hijack* (forged origin ASN; legitimate origin not in path).
- Apply RPKI ROV to BGP UPDATEs: a ROA is `(prefix, max-length, origin ASN)`. Validation returns `Valid`, `Invalid` (more-specific or wrong origin), or `NotFound` (no ROA covers it).
- Build a Python detector that consumes a stream of BGP UPDATEs, applies an import policy, and flags leak / hijack signatures.
- Produce an ingress policy runbook that combines RPKI ROV, IRR-based prefix lists, and `enforce-first-as`.

## The Problem

The on-call ticket reads: "From approximately 14:23 UTC, users in South America report 12-15% packet loss and 220 ms added latency reaching `203.0.113.0/24` (our customer-facing service). The same service responds normally from North America and Europe. A `traceroute` from a São Paulo host shows the path now goes through AS64666 (a regional ISP), not AS64600 (our usual transit). The BGP looking glass at `lg.as64600.net` confirms the change: the prefix is now visible with `AS_PATH = [64666 64555]` and `origin AS 64555` — not our usual `AS_PATH = [64600]`."

The first responder is the network operations team. They check their own announcements: `show bgp ipv4 unicast 203.0.113.0/24` shows the prefix originating from AS64600 normally, no withdrawal, no flap. They check the RPKI state: `rpki-client` shows a ROA covering `203.0.113.0/24` with `max-length 24` and `origin AS 64600`. They are still the rightful origin. The anomaly is purely external.

The second responder opens the RIPE RIS (Route Information Service) and `bgpstream` views. They see that AS64555 (a customer of AS64666) has been announcing `203.0.113.0/24` for the last 47 minutes. AS64555 has a customer-provider relationship with AS64666; AS64666 is propagating the leak to its peers. Because AS64666 does not run RPKI ROV and does not have an IRR-based prefix list filtering customers, the leak propagates.

The path `AS_PATH = [64666 64555]` tells a story: AS64555 originated the prefix (rightmost = origin), AS64666 received the route from its customer, and AS64666 propagated it to its peers. The path is internally consistent and BGP-valid; the leak is a *policy* failure, not a *protocol* failure. The fix is upstream: AS64666's import policy from AS64555 must be tightened.

The `code/main.py` simulator implements the import policy and the RPKI validator, and lets you walk through three scenarios: a clean (legitimate) UPDATE, a leaked UPDATE (real origin replaced by customer's transit-learned route), and a forged UPDATE (customer claims the origin AS in the path).

## The Concept

### The BGP UPDATE message structure

RFC 4271 §4.3 defines a BGP UPDATE as having three optional / variable sections, in order:

1. **Withdrawn Routes Length** (16 bits) + **Withdrawn Routes** (variable, IPv4 prefix + length encoding).
2. **Total Path Attribute Length** (16 bits) + **Path Attributes** (variable).
3. **NLRI** (variable) — the new reachable prefixes.

A path attribute is a TLV with:

- **Flags** (1 byte): bit 0 = optional, bit 1 = transitive, bit 2 = partial, bit 3 = extended-length. Well-known attributes (ORIGIN, AS_PATH, NEXT_HOP) have flag bit 0 = 0.
- **Type Code** (1 byte, 2 if extended-length is set).
- **Length** (1 or 2 bytes depending on extended-length flag).
- **Value** (variable).

| Type Code | Attribute | Flags | RFC |
|---|---|---|---|
| 1 | ORIGIN | well-known mandatory (00) | 4271 §5.1.1 |
| 2 | AS_PATH | well-known mandatory (00) | 4271 §5.1.2 |
| 3 | NEXT_HOP | well-known mandatory (00) | 4271 §5.1.3 |
| 4 | MULTI_EXIT_DISC (MED) | optional non-transitive (80) | 4271 §5.1.4 |
| 5 | LOCAL_PREF | well-known discretionary (40) | 4271 §5.1.5 |
| 8 | COMMUNITIES | optional transitive (c0) | 1997 |
| 16 | EXTENDED_COMMUNITIES | optional transitive (c0) | 4360 |
| 17 | AS4_PATH | optional transitive (c0) | 6793 |

The AS_PATH is composed of `AS_SEQUENCE` (type 1) and `AS_SET` (type 2) segments. RFC 4271 §5.1.2 requires at least one AS in the path; modern implementations also reject an empty AS_PATH and an AS_PATH that already contains the local AS (loop detection, RFC 4271 §6.3).

### The two distinct failure classes

**Route leak (RFC 7908 §2):** a customer AS receives a route via one transit provider and re-announces it to another transit provider, becoming an accidental transit. The origin AS is real and in the path; the leak is the *re-advertisement*. Effects: traffic blackholes (if the leaking AS has no upstream route to the victim) or takes a pathological path (if it does). MANRS (Mutually Agreed Norms for Routing Security) classifies route leaks into four types; types 1 (provider → customer) and 4 (customer → provider of another provider) are most common.

**AS path forgery / origin hijack:** an AS announces a prefix it does not own with a forged origin ASN. The path may be a single AS, or it may be a longer path designed to look plausible. Effects: traffic for the victim prefix is hijacked and sent to the attacker. The 2008 Pakistan / YouTube incident is the canonical example; AS17557 originated `208.65.153.0/24` as a /24 while YouTube's `208.65.152.0/22` was the legitimate block. The /24 was more specific, so longest-prefix-match routed traffic to AS17557.

The two classes overlap in symptom (traffic shift) but differ in mechanism: the leak has a real origin in the path, the hijack does not. RPKI catches the hijack cleanly (the origin is wrong → `Invalid`); RPKI does not catch the leak (the origin is right → `Valid`).

### RPKI and Route Origin Validation

RPKI (RFC 6480) is a public-key infrastructure that binds an ASN to a set of prefixes via signed Route Origin Authorizations (ROAs). A ROA contains `(prefix, max-length, origin ASN)` and is signed by the prefix's RPKI certificate. Routers fetch ROAs from the five Regional Internet Registries (RIPE, ARIN, APNIC, LACNIC, AFRINIC) via the rsync or RPKI-to-cache protocol (RFC 8210, RFC 6810).

When a BGP UPDATE arrives, the router runs RPKI ROV (RFC 6811):

- If a ROA exists and the UPDATE matches (prefix covered, length ≤ max-length, origin ASN matches): `Valid`.
- If a ROA exists and the UPDATE does NOT match: `Invalid`. The well-run network drops or depreferences `Invalid`.
- If no ROA exists for the prefix: `NotFound`. Most networks accept `NotFound` but with elevated preference or alarm.

Critical detail: ROV validates the *origin AS only*. It does not validate the AS_PATH. A leak with the right origin in the path is `Valid` and propagates. A hijack with a wrong origin is `Invalid` and is dropped.

### Why MAXPREFIX and prefix-lists are still needed

RPKI ROV catches origin hijacks. It does not catch:

- A more-specific hijack when the victim's ROA has a longer `max-length` (e.g. ROA allows up to /24, hijacker announces /25 from a different origin → still `Valid` for the /24, but the /25 is `Invalid` for any ROA matching the /25 — there is none, so `NotFound` is more typical, then longest-prefix-match picks the /25).
- A leak (origin is right, AS_PATH is internally consistent, RPKI returns `Valid`).
- An AS-path manipulation that does not change the origin.

The defense-in-depth is to combine RPKI ROV with:

- **IRR-based prefix lists**: each AS publishes its accepted customer set in an IRR (RIPE, ARIN, RADB); the receiving AS auto-generates `prefix-list` and `AS-path access-list` from those records.
- **`bgp enforce-first-as`** (Cisco) / `peer-allowas-in` controls: require the first AS in the received AS_PATH to match the peer's AS. Stops a peer from injecting a route it learned elsewhere.
- **`max-prefix`** per eBGP session: caps the number of prefixes accepted from a peer to bound the blast radius of an accidental full-table leak.
- **BGPsec** (RFC 8205): signature on AS_PATH so any insertion of an ASN is detectable. RPKI for the path, not just the origin. Deployment is still limited.

### The simulator's three scenarios

`code/main.py` consumes a stream of UPDATEs and applies (a) RPKI ROV against a small in-memory ROA table, (b) an import policy that checks the first AS equals the peer's AS (the `enforce-first-as` rule), and (c) a leak detector that flags UPDATEs whose origin AS is not the expected origin for the prefix. Three scenarios are wired:

1. `legitimate`: AS64600 originates `203.0.113.0/24` to AS64700. ROV: `Valid` (ROA exists, origin matches). Import policy: pass. Detector: no leak.
2. `route_leak`: AS64555 (a customer of AS64666) re-announces `203.0.113.0/24` to AS64666 with `AS_PATH = [64666 64555]`. ROV: `Valid` (origin AS64555 in path but ROV only checks the rightmost AS — wait, the rightmost is 64555, not 64600, so `Invalid` if a ROA says origin=64600, `NotFound` if no ROA). Detector: flags as leak.
3. `as_path_forgery`: AS64888 announces `203.0.113.0/24` with `AS_PATH = [64888]`. ROV: `Invalid` (ROA says origin=64600). Import policy: pass (no peer check). Detector: flags as origin mismatch.

## Build It

1. **Set up a tiny test lab.** Three FRR (Free Range Routing) containers connected in a chain: AS64600 (origin), AS64666 (transit), AS64888 (attacker). Each runs `bgpd`.
2. **Origin a prefix on AS64600.** `router bgp 64600; network 203.0.113.0/24; neighbor 64666 remote-as 64666` on the origin and `neighbor 64600 remote-as 64600` on the transit.
3. **Capture legitimate UPDATE.** `tcpdump -ni any -vvv -XX 'tcp port 179'` and identify the ORIGIN, AS_PATH, NEXT_HOP attributes.
4. **Inject the leak.** Configure AS64555 (another container) to `network 203.0.113.0/24` and `neighbor 64666 remote-as 64666`. Watch the transit propagate it to its peers.
5. **Run the simulator.** `python3 code/main.py --scenario route_leak` and confirm the detector flags the leak.
6. **Enable RPKI ROV in the transit.** `router bgp 64666; bgp rpki server 192.0.2.1 port 323; neighbor 64555 prefix-list AS64555-OUT out` — confirm the leak is dropped at the import filter.
7. **Ship the runbook.** A two-page ingress policy runbook with the ROV + prefix-list + max-prefix combination.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Inspect AS_PATH | `show bgp ipv4 unicast 203.0.113.0/24` | Origin AS matches the allocated owner (per WHOIS / IRR) |
| RPKI ROV state | `show bgp rpki` table | `Valid` for legit origin, `Invalid` for forged, `NotFound` for unassigned |
| Detect leak | Two transits see the same prefix from a shared customer | Customer should not be origin for transit-learned prefixes |
| enforce-first-as | Reject UPDATE whose first AS ≠ peering AS | Update dropped at import, log records the attempt |
| MAXPREFIX | `show ip bgp neighbor <x> summary` | Number of received prefixes never exceeds ceiling |
| Confirm impact | Traceroute from a third-party host | Path now enters the leaker AS before the victim AS |

## Ship It

Produce one reusable artifact under `outputs/`:

- A one-page **BGP ingress policy runbook** that combines RPKI ROV (reject `Invalid`), IRR-based prefix lists (customer → provider), `enforce-first-as`, and a MAXPREFIX ceiling.
- A looking-glass query template that returns the AS_PATH, RPKI state, and origin-asn history for any prefix.

Start from `outputs/prompt-bgp-route-leak-as-path-forgery.md` and paste in actual `show bgp` output from your test lab.

## Exercises

1. Construct an UPDATE whose `AS_PATH` is empty and explain why modern implementations reject it. Cite the RFC 4271 path-loop check that triggers.
2. Add a ROA for `203.0.113.0/24` with `origin AS64600, max-length 24` and re-run the forgery scenario. The simulator's verdict for the forged UPDATE should switch from `NotFound` to `Invalid`.
3. Reproduce a sub-prefix hijack: attacker announces `203.0.113.0/25` with `origin AS64888`. Explain why longest-prefix-match on a router that does not run ROV picks the /25, and why a ROA with `max-length 24` does *not* flag the /25 (it is `NotFound` because no ROA covers the /25 specifically).
4. Model a route leak where the customer prepends an extra ASN to AS_PATH to obscure the origin. Propose a detector that cross-checks the rightmost AS against the IRR AS-SET.
5. Evaluate the impact of `bgp route-map enforce-first-as` on leak containment. Why does it stop the in-lab leak but not the 2018 Amazon/DX incident (which was a leaked *transit* route, not a forged origin)?
6. Compare RPKI (RFC 6480) with BGPsec (RFC 8205). Why is BGPsec's deployment still under 5% of ASes? What is the political / operational blocker?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| AS_PATH | BGP attribute | Ordered list of ASNs the route traversed; rightmost is origin (RFC 4271 §5.1.2) |
| Route leak | Misannouncement | Customer exports routes learned from one transit to another; classified into 4 types by RFC 7908 |
| Origin hijack | Forgery | Attacker announces a prefix with its own AS as the claimed origin |
| RPKI | PKI for routing | Signed ROAs binding prefix to origin ASN; RFC 6480, RFC 6811 |
| ROA | Authorization | Route Origin Authorization: (prefix, max-length, origin ASN); RFC 6482 |
| ROV | Validation | Route Origin Validation: routers classify UPDATE as Valid/Invalid/NotFound; RFC 6811 |
| IRR | Database | Internet Routing Registry: AS-SET and route objects used to auto-generate filters |
| enforce-first-as | Peer check | First AS in received AS_PATH must equal the peer's AS; stops path-injection |
| MAXPREFIX | Ceiling | Hard cap on prefixes accepted per peer; bounds the blast radius of a misconfig |
| MANRS | Norms | Mutually Agreed Norms for Routing Security; industry initiative (route-leak prevention) |
| BGPsec | Signed path | Cryptographic signature on AS_PATH so any insertion is detectable; RFC 8205 |

## Further Reading

- RFC 4271 — A Border Gateway Protocol 4 (BGP-4) (UPDATE message, path attributes)
- RFC 1997 — BGP Communities Attribute (COMMUNITIES attribute)
- RFC 6480 — An Infrastructure to Support Secure Internet Routing (RPKI architecture)
- RFC 6482 — A Profile for Route Origin Authorizations (ROAs)
- RFC 6811 — BGP Prefix Origin Validation (ROV algorithm)
- RFC 7908 — Problem Definition and Classification of BGP Route Leaks (leak taxonomy)
- RFC 8205 — BGPsec Protocol Specification (signed AS_PATH)
- MANRS — Mutually Agreed Norms for Routing Security (operational guidance)
- RIPE Routing Information Service (RIS) — historical BGP update archive for forensics
