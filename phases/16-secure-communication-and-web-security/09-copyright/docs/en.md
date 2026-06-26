# Copyright

> Copyright in the network age is a synthesis of three legal traditions: the Berne Convention for literary and artistic works (1886, still in force), the WIPO Copyright Treaty of 1996 that added explicit protection for "computer programs" and "compilations of data," and the Digital Millennium Copyright Act (DMCA, 17 U.S.C. §1201) of 1998 that criminalizes the circumvention of "technological protection measures" — the copy-protection mechanisms in software, games, ebooks, and media files. For a network engineer, the practical consequence is that the bits moving on the wire are not yours to copy, the encryption keys guarding those bits are not yours to extract, and the access-control mechanisms enforcing the licensing are not yours to bypass — even if the underlying work is technically easy to duplicate. This lesson ships a stdlib-only Python tool (`code/main.py`) that walks through the four network-side mechanisms that copyright holders use (DRM licenses, watermarks, license servers, and takedown notices), explains why each one fails in a particular way, and gives a network engineer's checklist for handling copyright claims without violating the law or breaking the network.

**Type:** Learn
**Languages:** Python (stdlib only), openssl, browser tools, Wireshark
**Prerequisites:** Phase 16 lessons 01-08 (IPsec, firewalls, wireless security, PGP/S/MIME, threats, secure naming, SSL, mobile code)
**Time:** ~75 minutes

## Learning Objectives

- Identify the four legal frameworks that govern copyright in the network age (Berne, WIPO, DMCA, EUCD) and explain the role of each.
- Describe the four technical mechanisms that copyright holders use to enforce licensing on the network (DRM, watermarking, license servers, takedown notices).
- Recognize when a network engineer is asked to do something that may be a copyright violation (interception of protected streams, modification of DRM headers, replay of license tokens) and refuse appropriately.
- Configure a network to honor a takedown notice (DNS sinkhole, BGP blackhole, HTTP 451 response) without overblocking.
- Document the chain of evidence for a copyright claim (who sent the notice, what was claimed, what was removed) so the engineering team's actions are defensible.
- Identify the limits of the DMCA / EUCD safe-harbor provisions for network operators and the conditions under which the operator becomes liable.

## The Problem

You are the network engineering lead at NetCove Inc. Last Tuesday the legal team forwarded a takedown notice from a major movie studio: a NetCove-hosted website is allegedly streaming a copyrighted film without authorization. The notice contains a URL, a claim of copyright ownership, a sworn statement under penalty of perjury, and a request that the infringing material be removed "expeditiously." The legal team has asked you to "make this go away in 24 hours." The catch: the URL is a single page on a user-generated-content (UGC) site with 12 million pages, and you do not know which other pages may be infringing. The naive responses — sinkhole the whole domain, block the user's account, or shut down the site — each have their own legal and operational consequences, and a wrong move exposes NetCove to liability.

The deeper problem is that copyright and networks are in tension by design. The network is built to copy bits efficiently and globally; copyright is built to restrict copying for a limited time and territory. The DMCA's safe-harbor provision (17 U.S.C. §512) gives network operators a defense against monetary liability for user-posted content, but only if the operator responds "expeditiously" to takedown notices and meets a list of other conditions (designated agent, repeat-infringer policy, no actual knowledge). The 24-hour clock is the operator's friend (responding fast is the safe path) and the operator's enemy (responding without thinking is the unsafe path). The network engineer's job is to design a takedown process that is fast enough to satisfy the safe harbor and precise enough to avoid overblocking.

## The Concept

Source: `chapters/chapter-08-network-security.md` (legal aspects of computer security) and the DMCA / EUCD primary sources. The companion diagram is `assets/copyright.svg`.

### The four legal frameworks

The network-era copyright regime is a four-layer stack:

| Layer | Framework | Year | What it does |
|-------|-----------|------|--------------|
| 1. Base copyright | Berne Convention | 1886 | Establishes automatic copyright on creation (no registration required); minimum 50-year term; protects "literary and artistic works" |
| 2. Digital extension | WIPO Copyright Treaty (WCT) | 1996 | Adds explicit protection for "computer programs" and "compilations of data" (databases); requires "effective technological measures" be respected |
| 3. Anti-circumvention (US) | DMCA §1201 | 1998 | Criminalizes circumvention of "technological protection measures" (DRM) and trafficking in circumvention tools; exceptions for fair use, security research, encryption research |
| 4. Anti-circumvention (EU) | EUCD (Directive 2001/29/EC) | 2001 | EU analog of DMCA §1201; member states implement in national law (UK CDPA, German UrhG, French CPI) |

A network engineer is most likely to encounter the DMCA (US) and the EUCD (EU). The Berne Convention and the WCT are foundational but they shape the underlying rights, not the operational response.

### The four technical enforcement mechanisms

Copyright holders use four technical mechanisms to enforce licensing on the network:

1. **DRM (Digital Rights Management).** The content is encrypted with a key that the user receives only after authenticating with a license server. Examples: Widevine (Chrome, Android), FairPlay (Safari, iOS), PlayReady (Edge, Xbox). The license server can revoke the key, expire it, or refuse to issue a new one. The network engineer's role is limited: the DRM is enforced at the application layer, and the network just carries the encrypted bits.
2. **Watermarking.** A unique identifier is embedded in the content (visible or invisible) that traces the leak back to the specific user/license. Examples: AACS (Blu-ray), CMLA (mobile). The watermark survives transcoding in some cases. The network engineer's role is to preserve the watermark: do not transcode or recompress the user's content.
3. **License servers.** The content is freely downloadable, but the license to *use* it requires a server-issued token. Examples: Adobe Creative Cloud, Microsoft 365, most modern games. The network engineer may operate the license server (or its CDN front-end).
4. **Takedown notices.** The copyright holder does not prevent copying; they ask the operator to remove the infringing material after the fact. Examples: DMCA §512, EUCD Article 14. The network engineer is the front-line responder: the takedown notice arrives in legal's inbox, and legal forwards it to engineering to execute.

### The DMCA safe-harbor and the 24-hour clock

The DMCA §512 safe harbor protects a "service provider" from monetary liability for user-posted infringing material if the provider:

1. Does not have actual knowledge of the infringement, or acts expeditiously to remove it once aware.
2. Does not receive a financial benefit directly attributable to the infringing activity.
3. Responds expeditiously to remove or disable access to the material.
4. Has a designated agent registered with the U.S. Copyright Office.
5. Has a policy that terminates repeat infringers.
6. Accommodates standard technical measures (a controversial requirement that has been largely unused).

The 24-hour clock in the lesson's scenario is the "expeditious removal" requirement. The operator has 24 hours to remove or disable access; if they do, they keep the safe harbor. If they don't, they may lose it and become liable for statutory damages ($750-$30,000 per work, $150,000 for willful infringement).

The other side of the clock: if the operator removes material *without* a valid takedown notice, or removes *more* than the notice requests, they may face a counter-notice from the user under §512(g) and a possible lawsuit for improper removal. The 24-hour clock is therefore not a license to overblock.

### The takedown workflow

A defensible takedown workflow has six steps:

1. **Receive the notice.** Log the notice (PDF or email) in `legal/takedown-log.md` with date, sender, claimed work, URL, sworn statement, and signature.
2. **Validate the notice.** Check that the notice contains the six required elements under §512(c)(3): identification of the work, identification of the infringing material, contact information, good-faith statement, accuracy statement, signature.
3. **Locate the material.** The notice should contain a URL or a description sufficient to locate the material. If it does not, ask the sender for clarification; do not infer.
4. **Remove or disable access.** Three options, in increasing severity:
   - **Remove the specific URL** — the surgical option. DNS or HTTP redirect the URL to a "removed" page.
   - **Disable the user's account** — appropriate for repeat infringers or for material that the user can re-post trivially.
   - **Suspend the entire site** — only for sites dedicated to infringement (the "red flag" test from §512(d)(1)).
5. **Notify the user.** Send a counter-notice template to the user explaining what was removed and how to file a counter-notice under §512(g).
6. **Log the outcome.** Update `legal/takedown-log.md` with the action taken, the date, and the operator who executed it. This is the chain of evidence that demonstrates "expeditious removal" if the matter goes to court.

### The overblock failure modes

The most common overblock failure modes are:

- **Sinkholing the whole domain** when only one URL is infringing. This breaks every other user's content and exposes the operator to a counter-notice.
- **Blocking the user's IP address** at the firewall. This affects other users behind the same NAT and is rarely proportionate.
- **Refusing to act** because the notice looks fake. The DMCA requires action on a notice that *appears* valid; the operator's recourse is a counter-notice from the user, not inaction.
- **Acting on a foreign takedown** without verifying it meets US DMCA requirements. The DMCA does not apply to non-US operators, and a takedown from a foreign rightsholder may not be enforceable in the operator's jurisdiction.

The network engineer's checklist (Build It, step 3) walks through these.

## Build It

1. Read `code/main.py` and understand the data model: `TakedownLog` (case fields + workflow steps), `validate_notice()` (the §512(c)(3) check), `remove_url()` (the surgical option), `notify_user()` (the counter-notice template).
2. Run `python3 main.py` and walk through the demo: receive a notice, validate it, locate the URL, remove it, notify the user, log the outcome.
3. Walk through the network engineer's checklist (provided in `code/main.py` and reproduced below) for a hypothetical scenario where the notice points to a single URL on a UGC site with 12 million pages.
4. Modify the takedown log to add a second notice from a different rightsholder. Re-run and confirm the log records both.
5. Implement a counter-notice flow: when a user receives a takedown notification, they have 10-14 days to file a counter-notice. Add a `CounterNotice` dataclass and a `file_counter_notice()` method.
6. Implement a "no-action" branch: when a notice fails the §512(c)(3) validation (e.g., no signature), the operator must respond within a few days to the sender explaining why. Add a `reject_notice()` method and a template email.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|--------------------|
| Receive a takedown notice | Log entry with all 6 §512(c)(3) fields | Log entry dated, signed, in the takedown log |
| Validate the notice | `validate_notice()` returns True with all 6 fields present | True; if any field missing, return False and a list of missing fields |
| Locate the material | `locate_url()` returns the URL or a "not found" | URL or 404; never a guess |
| Remove the URL | `remove_url()` redirects the URL to a "removed" page | HTTP 410 Gone at the URL; other URLs unaffected |
| Notify the user | `notify_user()` sends the counter-notice template | Email sent within 24 hours; copy in `legal/takedown-log.md` |
| Log the outcome | `TakedownLog.append(outcome)` | Outcome has date, action, operator, URL |
| Handle a counter-notice | `file_counter_notice()` is called by the user | Counter-notice logged; user informed; material restored after 10-14 days unless rightsholder files suit |

## Ship It

Produce one artifact under `outputs/`:

- A "Takedown Response Runbook" suitable for the legal team's binder, with: the six-step workflow, the §512(c)(3) validation checklist, the four overblock failure modes, the counter-notice template, the "no-action" rejection template, and a worked example using a real-world takedown scenario.
- A 1-page "Takedown Notice Cheat Sheet" for the engineering team room wall, with: the 24-hour clock, the surgical / account / site options, the counter-notice 10-14 day window, and the safe-harbor conditions.

Start from [`outputs/prompt-copyright.md`](../outputs/prompt-copyright.md) and back every claim with a transcript from `code/main.py`.

## Exercises

1. Implement `validate_notice()` strictly per §512(c)(3) and add a unit test that fails the validation for each of the 6 missing fields. Confirm the failure messages identify which field is missing.
2. Add a `CounterNotice` dataclass and a `file_counter_notice()` method. Implement the 10-14 day waiting period: after a counter-notice is filed, the operator restores the material unless the rightsholder files suit within 14 days.
3. Add a "red flag" test: if the operator has actual knowledge that the material is infringing (e.g., a banner that says "Free movies!"), the safe harbor does not apply. Implement `has_red_flag(content)` and a test where a UGC page with a "free movies" banner fails the test.
4. Implement a takedown log query: given a date range, return all takedown notices, their actions, and their outcomes. Use it to compute the operator's average response time and the percentage of notices that resulted in a counter-notice.
5. Walk through a non-US scenario: a takedown notice arrives from a UK rightsholder for material hosted on a NetCove server in Frankfurt. Identify which jurisdiction's law applies and what the safe-harbor equivalent is.
6. Implement a takedown-rate-limit: a single rightsholder sending more than 100 notices per day may be abusing the system. Add a rate-limit check and a "review before action" branch.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Berne Convention | "the 1886 copyright treaty" | The base international copyright treaty; automatic copyright on creation, no registration required |
| WIPO Copyright Treaty | "the 1996 digital treaty" | International treaty adding explicit protection for computer programs and databases |
| DMCA §1201 | "the anti-circumvention law" | US law (17 U.S.C. §1201) criminalizing circumvention of DRM and trafficking in circumvention tools |
| DMCA §512 | "the safe harbor" | US law (17 U.S.C. §512) protecting service providers from monetary liability for user content if they meet 6 conditions |
| EUCD | "the EU copyright directive" | EU directive 2001/29/EC harmonizing copyright in the information society; member states implement in national law |
| DRM | "the copy protection" | Technical mechanism (Widevine, FairPlay, PlayReady) that encrypts content and gates decryption on a license |
| Watermark | "the hidden identifier" | A unique pattern embedded in content that traces a leak to a specific user/license |
| License server | "the activation server" | A server that issues a decryption key to a user after authenticating; can revoke, expire, or refuse |
| Takedown notice | "the DMCA notice" | A formal request from a rightsholder to remove infringing material; must contain 6 elements per §512(c)(3) |
| Counter-notice | "the user's response" | A formal response from the user claiming the material was removed in error; restores the material after 10-14 days unless the rightsholder sues |
| Safe harbor | "the operator's defense" | The §512 protection from monetary liability; lost if the operator does not respond expeditiously to a valid notice |
| Expeditiously | "in 24 hours" | The DMCA's expected response time for takedown removal; missing it can cost the safe harbor |

## Further Reading

- U.S. Copyright Office, *DMCA Section 512 Report* (2020) — the most comprehensive review of the safe-harbor provision, its application, and its reform proposals.
- World Intellectual Property Organization (WIPO), *WIPO Copyright Treaty* (1996) — the international treaty that added digital protections.
- European Union, *Directive 2001/29/EC* (EUCD) — the EU's anti-circumvention and copyright-harmonization directive.
- Litman, J. (2001). *Digital Copyright*, Prometheus Books — the legal scholar's view of copyright in the digital age.
- Gillespie, T. (2018). *Custodians of the Internet*, Yale University Press — platform moderation, takedown practices, and the safe-harbor regime in practice.
- Urban, J., Karaganis, J., and Schofield, B. (2017). *Notice and Takedown in Everyday Practice*, UC Berkeley — an empirical study of takedown practices on user-generated-content sites.
- Wikipedia, "DMCA," "WIPO Copyright Treaty," "EUCD," "DRM," "Widevine" — secondary references for cross-checking primary sources.
