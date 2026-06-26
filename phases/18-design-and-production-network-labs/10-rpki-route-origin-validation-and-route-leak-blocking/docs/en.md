# RPKI Route Origin Validation and Route-Leak Blocking in Production

> Every BGP-speaking network on the Internet is one misconfiguration or one malicious advertisement away from accepting a route to a prefix it does not own. The 2008 Pakistan Telecom / YouTube incident, the 2017 BGP hijack of a Brazilian bank, the 2018 Amazon DNS hijack, and the 2021 Facebook outage are all examples of **route leaks** and **prefix hijacks** that RPKI was designed to prevent. RPKI — Resource Public Key Infrastructure, specified in **RFC 6480 through RFC 6811** and updated by **RFC 8210** and **RFC 8893** — binds an IP prefix to an authorized origin AS using a chain of cryptographically signed certificates anchored in the RIRs (ARIN, RIPE, APNIC, LACNIC, AFRINIC). This lesson is the working playbook for a production AS that wants to (1) sign its own ROAs, (2) run a local RPKI validator (Routinator or rpki-client), (3) propagate the validated ROA payload (VRP) to every BGP speaker via the RPKI-to-Router protocol (RFC 8210), (4) enforce origin validation in the BGP best-path algorithm, and (5) detect and reject **route leaks** that bypass origin validation (e.g., a transit provider that re-originates a prefix from a customer without authorization). The deliverable is a Python RPKI validator that takes a BGP table dump, a set of ROAs, and a set of AS-path heuristics, and emits a per-prefix validation report with Invalid / Valid / NotFound / Leaked flags plus a remediation queue.

**Type:** Build
**Languages:** Python (stdlib only: dataclasses, ipaddress, json, base64, hashlib), shell, BGP, RPKI validators
**Prerequisites:** Phase 7 BGP, Phase 18 lesson 09 (BGP multihoming)
**Time:** ~140 minutes

## Learning Objectives

- Explain the **RPKI certificate hierarchy** (root, intermediate, end-entity CA) and how each RIR (ARIN, RIPE, APNIC) acts as a trust anchor for its allocated resources.
- Author a **ROA** (Route Origin Authorization, RFC 6482) that binds a prefix to an authorized origin AS, with a max-length constraint and a validity window.
- Operate an **RPKI validator** (Routinator, rpki-client, FORT) and understand the **RFC 8210** protocol that distributes Validated ROA Payloads (VRPs) to routers.
- Configure **BGP origin validation** on a router (Cisco IOS-XE `bgp origin-as validation`, Juniper `validation`, FRR's `rpki` module) and understand the three states: **Valid**, **Invalid**, and **NotFound**.
- Distinguish **origin validation** (is the prefix-AS pair authorized?) from **route-leak detection** (is the path going through a transit provider that should not see it?) and implement both with **RFC 9234** "ONLY TO CUSTOMER" / "ONLY TO PEER" AS-path filtering and **MANRS**-style peer-locking.
- Build a **monitoring pipeline** that consumes the validator's output, compares it to the live BGP table, and pages on any prefix that transitions from Valid to Invalid or that becomes an unexpected origin.

## The Problem

A regional tier-2 ISP, "NorthStar Networks" (AS 65020), has been told by its transit provider (AS 64600, "NorthCoast Networks" from lesson 09) that all customer BGP sessions must be RPKI-validating by the end of the quarter. NorthCoast has also informed NorthStar that it will start enforcing **RFC 9234** ("BGP AS-PATH Filtering Methods for Inter-AS Route Leaks") on its eBGP sessions, dropping any route that it receives from a customer but then sees being re-advertised to another customer. NorthStar's operations team must deliver four things: (1) sign ROAs for all 47 prefixes they originate, (2) deploy a Routinator instance in their network operations center, (3) configure origin validation on all 12 BGP speakers, (4) deploy route-leak detection that compares the AS-path of every received route against a customer/cone/peering table.

The most painful part of RPKI is not the cryptographic chain — it is the **operational coordination**. A ROA that is too permissive (a max-length of /16 when the prefix is /24) lets an attacker advertise a more-specific /25 or /26 and bypass the origin validation (the /25 is more specific, so the longest-match rule wins, and the attacker can attract traffic for a portion of the prefix). A ROA that is too restrictive (max-length /24 when the customer has /25 sub-prefixes) breaks the customer's own announcements. A ROA that is signed but not published in the RIR's repository is invisible to validators. A ROA that is published but for which the validator has not yet fetched the manifest is invisible until the next refresh (default 60 minutes, configurable down to 1 minute).

The route-leak problem is even more nuanced. Origin validation answers "is this prefix-AS pair authorized?" Route-leak detection answers "did the AS-path include an AS that should not see this route?" The two are orthogonal: a perfectly valid origin (the prefix-AS is authorized) can still be leaked (an AS that is not a provider of the origin AS is in the path). RFC 9234 defines two leak types — **type U** (upstream-to-upstream leak, e.g., one provider's customer route appearing in another provider's table) and **type L** (lateral leak, e.g., one peer's customer route appearing in another peer's table) — and provides a heuristic for inferring the customer/provider/peer role of each AS hop from the AS-path. The lesson's planner implements the RFC 9234 role-inference heuristic and flags any route whose path violates the inferred role graph.

## The Concept

RPKI is a **public key infrastructure** for IP address space, modeled loosely on X.509 PKI but specialized for routing. The certificates are short-lived (the end-entity EE certificates that sign ROAs are valid for a year or less), the manifests are hourly (each repository publishes a manifest every 60 minutes so a validator can detect tampering), and the trust anchors are the RIRs (each RIR publishes its own public key and signs the certificates of its member organizations).

### RPKI certificate hierarchy and the trust chain

The **RPKI trust anchors** are the five RIRs: ARIN (North America), RIPE NCC (Europe / Middle East / Central Asia), APNIC (Asia / Pacific), LACNIC (Latin America / Caribbean), and AFRINIC (Africa). Each RIR holds a self-signed root certificate and uses it to sign the certificates of the organizations that hold address space in its region. The organization (NorthStar Networks in our example) receives a signed certificate that authorizes it to make statements about the prefixes it has been allocated, and uses that certificate to sign its own ROAs.

The chain is:

```
RIR root certificate (e.g., ARIN self-signed, trust anchor)
  |
  +-- RIR intermediate CA certificate (optional, many RIRs use direct delegation)
        |
        +-- Organization end-entity certificate (e.g., NorthStar's CA)
              |
              +-- ROA (Route Origin Authorization) for 198.51.100.0/24, AS65020
              +-- ROA for 198.51.100.128/25, AS65020
              +-- ROA for 203.0.113.0/24, AS65020, max-length 24
```

A validator starts with the trust anchor (downloaded once and stored in a local file), follows the chain to the ROA, and produces a **Validated ROA Payload (VRP)** — a tuple of (prefix, prefix-length, max-length, origin AS, validity window). The validator caches the VRPs and serves them to BGP speakers via RFC 8210 (the "RPKI to Router" protocol, which uses a TCP session, a freshness check, and a serial-number-based cache-invalidation mechanism).

The **manifest** (RFC 6486) is the file that lists all the objects (ROAs, Ghostbusters records) in a CA's repository at a point in time. A validator uses the manifest to detect tampering: if the manifest says the repository contains 47 ROAs but the validator only fetches 46, the 47th is either missing (deleted) or corrupted (the signature does not verify). The manifest is signed by the CA's certificate and contains the URI of every object, the object's hash, and the validity window. The standard refresh interval is 60 minutes; a vigilant operator can set it to 1-10 minutes to detect hijacks faster at the cost of more outbound traffic to the RIR repositories.

### ROA authoring and the max-length trap

A ROA is a small signed object that contains four fields: the **prefix** (in CIDR notation), the **prefix-length** (the length of the prefix itself, not the max-length), the **max-length** (the most-specific prefix that may be advertised with this origin AS), and the **origin AS** (the AS authorized to originate the prefix).

The **max-length trap** is the most common ROA misconfiguration. Consider a customer that holds 198.51.100.0/24 and advertises both 198.51.100.0/24 and 198.51.100.128/25 (a more-specific). If the ROA is authored as `198.51.100.0/24 max-length 24`, then the /25 advertisement is **Invalid** (the max-length is 24, so /25 is not allowed) and the customer's more-specific is rejected. If the ROA is authored as `198.51.100.0/24 max-length 25`, then the /25 advertisement is **Valid** and the customer's more-specific is accepted.

The inverse is the "too permissive" trap: if the ROA is `198.51.100.0/24 max-length 16`, then an attacker can advertise a more-specific /17, /18, ..., /24 from a different AS, and the attacker's advertisement is **Valid** for the /17-/24 range (because the max-length is 16) — but the attacker's /24 is more-specific than the legitimate /24, so longest-match wins and the attacker attracts traffic for the /24. The lesson's planner enforces a "max-length equals prefix-length" default and warns when the operator overrides it.

The **validity window** is the time interval during which the ROA is honored. A ROA typically has a `notBefore` and `notAfter` timestamp; a validator ignores the ROA outside this window. The default is one year from signing, but production deployments use 3-12 month windows and re-sign the ROA before expiration. A ROA that expires without renewal causes the prefix to transition from Valid to NotFound, which is a soft error (the route is accepted but the validation flag is NotFound) but is operationally equivalent to losing the ROA.

### Origin validation states and the BGP best-path extension

When a router receives a BGP route and has a VRP table (populated by the validator via RFC 8210), the router performs **origin validation** for each route. The validation result is one of three states, defined in **RFC 6811** and updated by **RFC 9319**:

- **Valid**: there is at least one VRP that matches the prefix, and the origin AS in the BGP route matches the origin AS in the VRP, and the prefix-length of the route is greater-than-or-equal-to the prefix-length of the VRP and less-than-or-equal-to the max-length of the VRP.
- **Invalid**: there is at least one VRP that covers the prefix (i.e., the prefix is within the VRP's range) but the origin AS in the BGP route does not match the origin AS in any matching VRP, or the prefix-length is more-specific than the max-length.
- **NotFound**: there is no VRP that covers the prefix. The route is accepted by origin validation; the absence of a VRP is treated as no opinion.

The router then applies the **BGP best-path extension**: by default, a route marked **Invalid** is rejected (the route is dropped from the BGP table and not advertised further). A route marked **Valid** is preferred over a route marked **NotFound** for the same prefix (this is a configurable knob; some operators prefer Valid over NotFound, others treat them equally). A route marked **NotFound** is treated as no opinion and accepted as if validation were not running.

The **Invalid→reject default** is the security primitive. Without it, RPKI is informational only and an attacker can still hijack the prefix; with it, an attacker who advertises a more-specific Invalid route is dropped at the first RPKI-validating router, and the attack fails. The lesson's planner emits the BGP configuration to set `bgp origin-as validation signal ibgp` (Cisco) or `set protocols bgp bestpath roa-valid` (Juniper) or `rpki` (FRR) and to log any Invalid route to a syslog destination for security monitoring.

### Route-leak detection and RFC 9234

Origin validation does not catch **route leaks**. A route leak is a route that is valid in origin (the prefix-AS is authorized) but is propagated through an AS that should not see it. The classic example: AS A has a customer C that originates prefix P. AS A advertises P to its provider P'. AS P' leaks P to its other customer D, which has no business relationship with C. P is now in D's table, D's outbound traffic to P goes through P' instead of through A, and P' becomes a free transit for C→D traffic.

**RFC 9234** ("BGP AS-PATH Filtering Methods for Inter-AS Route Leaks") formalizes the problem and provides a detection heuristic. The RFC defines the **AS-path role inference**: for each AS in the AS-path, infer whether the AS is acting as a **provider** (upstream), **customer** (downstream), or **peer** (lateral) relative to the previous AS in the path. A leak occurs when the inferred role chain is inconsistent: e.g., an AS receives a route from a provider, then advertises it to another provider (provider-to-provider leak), or an AS receives a route from a peer, then advertises it to a provider (peer-to-provider leak).

The role inference uses the **AS-rank** data published by CAIDA (the Center for Applied Internet Data Analysis), which classifies each AS as a tier-1 transit provider, a tier-2, a content provider, or a customer. The lesson's planner bundles a small AS-rank table and uses it to infer the role of each hop. The planner then applies the RFC 9234 rules:

- **Rule 1 (only-to-customer)**: a route learned from a provider may be advertised only to customers.
- **Rule 2 (only-to-peer)**: a route learned from a peer may be advertised only to customers (not to other providers or peers).
- **Rule 3 (no-valley-free violation)**: the AS-path must be valley-free: customer→provider→peer→provider→customer is allowed, but customer→provider→customer→provider is not.

The planner flags any route that violates the rules and reports the violating hop.

### Monitoring, alerting, and the hijack response runbook

RPKI is not a "set and forget" technology. A prefix can transition from Valid to Invalid for any of several reasons: the ROA has expired, the validator has a stale cache, the RIR repository is unavailable, or — most importantly — an attacker is advertising a more-specific Invalid route. The monitoring pipeline must detect all of these.

The lesson's `code/main.py` implements a monitoring pipeline that:

1. Polls the validator's VRP table every 60 seconds.
2. Compares the current VRP table to the previous one and logs any change (new VRP, removed VRP, modified max-length).
3. Polls the BGP table (via `show ip bgp` or equivalent) and flags any prefix whose origin validation state has changed.
4. Maintains a per-prefix history of validation states and computes a 24-hour summary (number of state transitions, total time in each state, longest Valid streak).
5. Generates an alert if a prefix transitions from Valid to Invalid (likely hijack attempt) and pages the on-call.

The runbook includes the email template to the upstream NOC, the RFC 7908 e-mail format for security incidents, and the AS-path evidence to attach. The lesson's planner outputs the runbook as a markdown file in `outputs/rpki_runbook.md`.

## Build It

The deliverable is `code/main.py`, a deterministic RPKI validator and route-leak detector. Inputs are: a list of ROAs (with prefix, prefix-length, max-length, origin AS, validity window), a BGP table dump (a list of prefixes with origin AS and AS-path), and an AS-rank table (a small JSON file with tier classification per AS). Outputs are: a per-prefix validation report (Valid / Invalid / NotFound), a route-leak report (which routes violate RFC 9234), a per-prefix state-transition history, and a runbook template.

Run it: `python3 code/main.py`. The output is a JSON report and a human-readable printout. The printout includes:

- A **VRP table** derived from the ROAs, with each VRP tagged Valid / Invalid / NotFound.
- A **per-prefix origin-validation report** with the validation state for every prefix in the BGP table.
- A **route-leak report** with the violating hop for each leaked route.
- A **monitoring summary** with the number of state transitions per prefix and the longest Valid streak.
- A **runbook template** with the email template, the AS-path evidence, and the escalation contacts.

## Use It

| Deliverable | Acceptance Criteria | Status |
|-------------|---------------------|--------|
| VRP table | Every ROA produces exactly one VRP; VRPs are time-filtered; VRP table size matches ROA count | Pass |
| Origin validation report | Per-prefix Valid/Invalid/NotFound state; matches the RFC 6811 algorithm | Pass |
| Route-leak report | Every RFC 9234 rule violation is flagged with the violating hop and the rule name | Pass |
| State-transition history | Every state change is recorded; 24-hour summary per prefix | Pass |
| Monitoring summary | Total transitions, longest Valid streak, alert threshold (≥ 1 transition) | Pass |
| Runbook | Email template, AS-path evidence, escalation contacts | Pass |
| Negative tests | Empty ROA list, empty BGP table, conflicting ROAs, expired ROAs all handled | Pass |
| JSON output | Machine-readable, parseable, schema-validated | Pass |

## Ship It

The artifact is `outputs/rpki_report.json` plus the printout. The JSON includes the VRP table, the per-prefix validation report, the route-leak report, the state-transition history, and the monitoring summary. The printout is the human-readable report that goes to the NOC. The output directory should also contain `rpki_runbook.md` (the cutover and incident-response runbook) and a `vrps.json` (the current VRP table in the format used by Routinator).

## Exercises

1. **ROA with conflicting max-length.** A customer has 198.51.100.0/24 and advertises both 198.51.100.0/24 and 198.51.100.128/25. Author the ROAs for both advertisements. What is the minimum set of ROAs that covers both? What happens if the max-length is 25 vs 24?

2. **Hijack scenario modeling.** An attacker advertises 198.51.100.0/24 from AS 65999 (a different origin from the legitimate AS 65020). What is the origin-validation state of the attacker's advertisement if there is a ROA for 198.51.100.0/24, AS 65020? What if the max-length is 25 and the attacker advertises a more-specific /25? How does the BGP longest-match rule interact with the RPKI origin-validation state?

3. **RFC 9234 leak detection.** Build a BGP table with three routes: (a) A→B→C, (b) A→B→D→C, (c) A→E→C. Suppose B and E are providers, C and D are customers. Which routes are leaked? Which RFC 9234 rule is violated?

4. **ROA expiry and the NotFound transition.** A ROA is signed with a one-year validity. After 364 days, the operator has not renewed. What is the origin-validation state of the prefix? What should the monitoring pipeline do?

5. **Validator outage and the stale cache.** The RIR repository is down for 4 hours. The validator cannot refresh its manifest. What is the impact on the VRP table? What is the operational impact on BGP?

6. **Multi-RIR trust anchors.** A network holds space in both ARIN and APNIC. How is the RPKI trust chain built? How does the validator handle two trust anchors? What is the policy when a manifest from one RIR is delayed?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| RPKI | "Signed authorization for prefix origination" | A PKI hierarchy anchored in the RIRs that cryptographically binds prefixes to authorized origin ASes |
| ROA | "Authorization to originate a prefix" | A signed object (RFC 6482) that authorizes a specific AS to originate a specific prefix up to a max-length |
| VRP | "Validated ROA Payload" | A (prefix, max-length, origin AS) tuple derived from a ROA and stored in the validator's cache |
| Trust anchor | "The root of the chain" | The RIR's self-signed root certificate, the starting point for chain validation |
| Manifest | "Signed list of objects in a repository" | A signed file (RFC 6486) that enumerates every object in a CA's repository and detects tampering |
| RFC 8210 | "RPKI to router protocol" | The protocol by which routers fetch VRPs from a validator |
| Origin validation | "Is the prefix-AS pair authorized?" | A check against the VRP table that returns Valid, Invalid, or NotFound for each route |
| Route leak | "A route is in the wrong place" | A route that is valid in origin but is propagated through an AS that should not see it (RFC 9234) |
| Longest-match | "Most-specific prefix wins" | The BGP tiebreaker that prefers a more-specific prefix over a less-specific one, even if the less-specific has a shorter AS-path |
| Validity window | "The ROA is valid from-to" | A pair of timestamps on the ROA that define when the ROA is honored by a validator |

## Further Reading

- **RFC 6480-6487** — *An Infrastructure to Support Secure Internet Routing* — the RPKI architecture
- **RFC 6482** — *A Profile for Route Origin Authorizations (ROAs)* — the ROA format
- **RFC 6486** — *Manifests for the RPKI* — the manifest format
- **RFC 6810, 6811** — *The RPKI to Router Protocol* — original protocol
- **RFC 8210** — *The RPKI to Router Protocol* — production protocol
- **RFC 8893** — *Origin Validation for BGP Route Leaks* — origin-validation extensions
- **RFC 9234** — *BGP AS-PATH Filtering Methods for Inter-AS Route Leaks* — route-leak detection
- **RFC 7908** — *Format for an e-mail Bilateral Peering and Security Specification* — security incident e-mail format
- **NLnet Labs Routinator documentation** — open-source RPKI validator
- **RIPE NCC RPKI documentation** — RIPE's RPKI portal and tools
- **ARIN RPKI documentation** — ARIN's RPKI portal
- **MANRS (Mutually Agreed Norms for Routing Security)** — industry routing-security baseline
- **CAIDA AS-rank** — AS relationship classification dataset
- **Cloudflare RPKI dashboard** — public view of RPKI validation rate
